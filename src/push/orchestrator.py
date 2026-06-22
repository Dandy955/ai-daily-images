#!/usr/bin/env python
import os
import re
import sys
import json
import socket
import logging
import argparse
from datetime import datetime
from pathlib import Path

from src.config import (
    load_push_config, get_user_id_name_map,
    get_feedback_config, PROJECT_DIR
)

SCRIPT_DIR = Path(__file__).parent.parent.parent / '03-本地推送服务'
OUTPUT_DIR = PROJECT_DIR / '04-AI日报' / 'output'

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def load_push_config_safe(test_mode):
    try:
        return load_push_config(test_mode)
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        return None


def find_today_report():
    try:
        if not OUTPUT_DIR.exists():
            logger.error(f"输出目录不存在: {OUTPUT_DIR}")
            return None
        today_str = datetime.now().strftime('%Y%m%d')
        files = list(OUTPUT_DIR.glob(f'AI日报_{today_str}*.png'))
        if not files:
            logger.warning(f"今日日报不存在 ({today_str})")
            return None
        latest = max(files, key=lambda p: p.stat().st_mtime)
        logger.info(f"找到今日日报: {latest.name}")
        return latest
    except Exception as e:
        logger.error(f"查找日报失败: {e}")
        return None


def check_network():
    targets = [
        ("qyapi.weixin.qq.com", 443, "企微API"),
        ("api.github.com", 443, "GitHub API"),
        ("smtp.qq.com", 465, "SMTP"),
    ]
    failures = []
    for host, port, name in targets:
        try:
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
        except Exception as e:
            failures.append(f"{name}({host}:{port})")
    return len(failures) == 0, failures


def push_to_email(image_path, config):
    email_cfg = config.get('推送渠道', {}).get('邮件', {})
    if not email_cfg.get('启用', False):
        return False, "未启用"
    from src.push.email_sender import send_email_with_news_summary
    recipients = email_cfg.get('接收人', '')
    if not recipients:
        return False, "未配置收件人"
    recipient_list = [r.strip() for r in recipients.split(';') if r.strip()]
    ok = 0
    for r in recipient_list:
        if send_email_with_news_summary(str(image_path), r):
            ok += 1
    success = ok > 0
    return success, f"{ok}/{len(recipient_list)} 成功"


def push_to_wecom_api(image_path, config, img_url=None, github_ok=True):
    wecom_cfg = config.get('推送渠道', {}).get('企业微信', {})
    if not wecom_cfg.get('启用', False):
        return False, "未启用"
    from src.push.wecom import push_via_wecom_api_news
    users = wecom_cfg.get('接收人', {}).get('用户ID', '')
    if not users:
        return False, "未配置接收人"
    result = push_via_wecom_api_news(str(image_path), users, img_url=img_url, github_ok=github_ok)
    if isinstance(result, tuple):
        return result
    return result, "成功" if result else "失败"


def push_to_wecom_webhook(image_path, config, img_url=None, github_ok=True):
    wecom_cfg = config.get('推送渠道', {}).get('企业微信', {})
    webhook_cfg = wecom_cfg.get('Webhook', {})
    if not webhook_cfg.get('启用', False):
        return False, "未启用"
    import os as _os
    webhook_key = _os.environ.get('WECOM_WEBHOOK_KEY', '')
    if not webhook_key:
        return False, "未配置Webhook Key"
    from src.push.wecom import send_webhook_news
    result = send_webhook_news(webhook_key, str(image_path), img_url=img_url, github_ok=github_ok)
    if isinstance(result, tuple):
        return result
    return result, "成功" if result else "失败"


def record_push_result(config, image_path, wecom_api_result, email_result, webhook_result, push_type="正式"):
    try:
        log_file = SCRIPT_DIR / 'push_log.json'
        history = []
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                if not isinstance(history, list):
                    history = [history]
            except Exception:
                history = []

        record = {
            "日期": datetime.now().strftime('%Y-%m-%d'),
            "时间": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "类型": push_type,
            "日报文件": str(image_path) if image_path else None,
            "推送结果": {
                "企业微信应用": {"状态": "成功" if wecom_api_result[0] else "失败", "详情": wecom_api_result[1]},
                "邮件": {"状态": "成功" if email_result[0] else "失败", "详情": email_result[1]},
                "Webhook群": {"状态": "成功" if webhook_result[0] else "失败", "详情": webhook_result[1]},
            }
        }
        history.append(record)
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        logger.info(f"推送日志已记录")
    except Exception as e:
        logger.error(f"记录日志失败: {e}")


def send_feedback(config, image_path, wecom_api_result, email_result, webhook_result, test_mode=False):
    fb = get_feedback_config()
    user_map = get_user_id_name_map(config)
    wecom_cfg = config.get('推送渠道', {}).get('企业微信', {})
    email_cfg = config.get('推送渠道', {}).get('邮件', {})

    wecom_ok, wecom_detail = wecom_api_result
    email_ok, email_detail = email_result
    webhook_ok, webhook_detail = webhook_result

    today = datetime.now().strftime('%Y-%m-%d')
    time_str = datetime.now().strftime('%H:%M:%S')

    if test_mode:
        email_recipients = email_cfg.get('接收人', '')
        wecom_recipients = wecom_cfg.get('接收人', {}).get('用户ID', '') if wecom_cfg.get('启用', False) else '未启用'

        parts = [f"🧪 [测试] AI日报推送结果反馈 ({today})"]
        parts.append("")
        parts.append(f"🖼️ 日报文件：{image_path.name if image_path else '无'}")
        parts.append("")

        if wecom_cfg.get('启用', False):
            all_ids = [u.strip() for u in wecom_recipients.split('|') if u.strip()]
            failed_ids = []
            if isinstance(wecom_detail, str) and '失败用户' in wecom_detail:
                after = wecom_detail.split('失败用户')[-1].strip()
                after = after.split('：')[-1].strip() if '：' in after else after.split(':')[-1].strip() if ':' in after else after
                failed_ids = [u for u in after.split('|') if u.strip() and re.fullmatch(r'[\w]{4,20}', u)]
            success_ids = [u for u in all_ids if u not in failed_ids]
            if not success_ids and not failed_ids:
                status_text = "⚠️ 未知"
            elif not failed_ids:
                status_text = "✅ 全部成功"
            elif not success_ids:
                status_text = "❌ 全部失败"
            else:
                status_text = "⚠️ 部分成功"
            parts.append("📱 企业微信应用推送（比干/企服司南）：")
            parts.append(f"   状态：{status_text}")
            if success_ids:
                names = [f"{user_map.get(u, u)}（{u}）" for u in success_ids]
                parts.append(f"   成功：{'；'.join(names)}")
            if failed_ids:
                names = [f"{user_map.get(u, u)}（{u}）" for u in failed_ids]
                parts.append(f"   失败：{'；'.join(names)}")
            if not success_ids and not failed_ids:
                parts.append(f"   备注：{wecom_detail}")
            parts.append("")

        parts.append("📧 邮件推送：")
        parts.append(f"   接收人：{email_recipients}")
        parts.append(f"   状态：{'✅ 成功' if email_ok else '❌ 失败'} ({email_detail})")
        parts.append("")
        parts.append("---")
        parts.append(f"⏰ 推送时间：{time_str}")

        text = '\n'.join(parts)
        subject = f"🧪 [测试] AI日报推送结果 ({today})"
    else:
        wecom_lines = ""
        if wecom_cfg.get('启用', False):
            all_ids = [u.strip() for u in wecom_cfg.get('接收人', {}).get('用户ID', '').split('|') if u.strip()]
            failed_ids = []
            if isinstance(wecom_detail, str) and '失败用户' in wecom_detail:
                after = wecom_detail.split('失败用户')[-1].strip()
                after = after.split('：')[-1].strip() if '：' in after else after.split(':')[-1].strip() if ':' in after else after
                failed_ids = [u for u in after.split('|') if u.strip() and re.fullmatch(r'[\w]{4,20}', u)]
            success_ids = [u for u in all_ids if u not in failed_ids]
            if not success_ids and not failed_ids:
                status_text = "⚠️ 未知"
            elif not failed_ids:
                status_text = "✅ 全部成功"
            elif not success_ids:
                status_text = "❌ 全部失败"
            else:
                status_text = "⚠️ 部分成功"
            parts = ["📱 企业微信应用推送（比干/企服司南）："]
            parts.append(f"   状态：{status_text}")
            if success_ids:
                names = [f"{user_map.get(u, u)}（{u}）" for u in success_ids]
                parts.append(f"   成功：{'；'.join(names)}")
            if failed_ids:
                names = [f"{user_map.get(u, u)}（{u}）" for u in failed_ids]
                parts.append(f"   失败：{'；'.join(names)}")
            if not success_ids and not failed_ids:
                parts.append(f"   备注：{wecom_detail}")
            wecom_lines = '\n'.join(parts) + '\n'

        email_recipients = email_cfg.get('接收人', '') if email_cfg.get('启用', False) else '未启用'
        text = (
            f"📋 AI日报推送结果反馈 ({today})\n\n"
            f"🖼️ 日报文件：{image_path.name if image_path else '无'}\n\n"
            f"{wecom_lines}\n"
            f"📧 邮件推送：\n"
            f"   接收人：{email_recipients}\n"
            f"   状态：{'✅ 成功' if email_ok else '❌ 失败'} ({email_detail})\n\n"
            f"🤖 Webhook群推送：\n"
            f"   状态：{'✅ 成功' if webhook_ok else '❌ 失败'} ({webhook_detail})\n"
            f"---\n"
            f"⏰ 推送时间：{time_str}"
        )
        subject = f"📋 AI日报推送结果 ({today})"

    from src.push.wecom import get_access_token, _send_text as send_text
    token = get_access_token()
    if token:
        send_text(token, text, fb['wecom_user'])

    from src.push.email_sender import send_simple_email
    send_simple_email(fb['email'], subject, text)


def notify_no_report(today_str):
    fb = get_feedback_config()
    msg = (
        f"AI日报推送提醒 ({today_str})\n\n"
        f"今日日报未生成，本次推送已跳过。\n"
        f"时间：{datetime.now().strftime('%H:%M:%S')}"
    )
    from src.push.wecom import get_access_token, _send_text as send_text
    token = get_access_token()
    if token:
        send_text(token, msg, fb['wecom_user'])
    from src.push.email_sender import send_simple_email
    send_simple_email(fb['email'], f"AI日报未生成 ({today_str})", msg)


def do_push(report, config, test_mode=False):
    from src.push.wecom import upload_image_to_github

    logger.info("上传图片到GitHub图床...")
    github_ok = False
    github_url = None
    try:
        ok, result = upload_image_to_github(str(report))
        if ok:
            github_url = result
            github_ok = True
            logger.info(f"GitHub上传成功")
        else:
            logger.warning(f"GitHub上传失败，将降级")
    except Exception as e:
        logger.warning(f"GitHub上传异常，将降级: {e}")

    logger.info("推送中...")
    email_result = push_to_email(report, config)

    if test_mode:
        logger.info("测试模式：跳过Webhook（企微应用正常推送给本人）")
        webhook_result = (False, "测试模式已跳过")
    else:
        webhook_result = push_to_wecom_webhook(report, config, img_url=github_url, github_ok=github_ok)

    wecom_api_result = push_to_wecom_api(report, config, img_url=github_url, github_ok=github_ok)

    return github_ok, email_result, webhook_result, wecom_api_result


def main():
    parser = argparse.ArgumentParser(description='AI日报推送服务')
    parser.add_argument('--test', action='store_true', help='测试模式：仅邮件发送给本人')
    parser.add_argument('--repush', action='store_true', help='补推模式')
    args, _ = parser.parse_known_args()

    logger.info("=" * 50)
    logger.info(f"AI日报推送服务 {'[测试模式]' if args.test else '[正式]'}")
    logger.info("=" * 50)

    log_file = SCRIPT_DIR / 'push_log.json'

    if not args.test and not args.repush:
        history = []
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                if not isinstance(history, list):
                    history = [history]
            except Exception:
                history = []
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_count = sum(1 for p in history if p.get('日期') == today_str)
        if today_count >= 1:
            logger.warning(f"今日已有 {today_count} 次推送记录，跳过（使用 --repush 强制补推）")
            return True

    config = load_push_config_safe(args.test)
    if not config:
        return False

    if not args.test:
        net_ok, failures = check_network()
        if not net_ok:
            logger.warning(f"网络预检失败: {failures}")

    report = find_today_report()
    if not report:
        today_str = datetime.now().strftime('%Y%m%d')
        notify_no_report(today_str)
        return False

    push_type = "测试" if args.test else "正式"
    if args.repush:
        push_type = "补推"

    github_ok, email_result, webhook_result, wecom_api_result = do_push(report, config, args.test)

    all_failed = not (wecom_api_result[0] or email_result[0] or webhook_result[0])
    if all_failed and not args.test:
        logger.warning("全部失败，30秒后重试...")
        import time
        time.sleep(30)
        github_ok, email_result, webhook_result, wecom_api_result = do_push(report, config, args.test)

    record_push_result(config, report, wecom_api_result, email_result, webhook_result, push_type)
    send_feedback(config, report, wecom_api_result, email_result, webhook_result, test_mode=args.test)

    logger.info("=" * 50)
    logger.info(f"邮件: {'成功' if email_result[0] else '失败'} ({email_result[1]})")
    logger.info(f"企微应用: {'成功' if wecom_api_result[0] else '失败'} ({wecom_api_result[1]})")
    if not args.test:
        logger.info(f"Webhook: {'成功' if webhook_result[0] else '失败'} ({webhook_result[1]})")
    logger.info("=" * 50)

    return any([email_result[0], webhook_result[0], wecom_api_result[0]])


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"异常: {e}", exc_info=True)
        sys.exit(1)
