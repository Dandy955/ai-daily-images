import json
import base64
import hashlib
import logging
from datetime import datetime
from pathlib import Path
import requests

from src.config import get_wecom_config, get_github_config, PROJECT_DIR

logger = logging.getLogger(__name__)

GITHUB_HEADERS = {}
_gh = get_github_config()
if _gh['token'] and _gh['owner'] and _gh['repo']:
    GITHUB_HEADERS = {
        "Authorization": "token " + _gh['token'],
        "Accept": "application/vnd.github.v3+json"
    }


def get_news_summary():
    today_str = datetime.now().strftime('%Y%m%d')
    summary_path = PROJECT_DIR / '04-AI日报' / f'AI日报_{today_str}_summary.json'

    default = (
        f"AI日报 {today_str}\n\n点击封面图查看完整日报内容"
    )

    try:
        if not summary_path.exists():
            return default
        with open(summary_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        lines = []
        img_news = data.get('img_news', [])
        tool = data.get('tool', {})
        case = data.get('case', {})

        if img_news:
            first = img_news[0] if isinstance(img_news[0], str) else img_news[0].get('title', '')
            lines.append(("AI要闻", 0))
            lines.append((f"  {first}", 0))
            lines.append(("", 0))

        if tool:
            name = tool.get('name', '')
            lines.append((f"AI工具：{name}", 4))
            scene = tool.get('scene', '')
            if scene:
                lines.append((f"  场景：{scene}", 3))
            suitable = tool.get('suitable', '') or tool.get('fit_for', '')
            if suitable:
                lines.append((f"  适合：{suitable}", 3))
            steps = tool.get('steps', '')
            if steps:
                lines.append((f"  上手：{steps}", 3))
            lines.append(("", 4))

        if case:
            name = case.get('name', '')
            content = case.get('content', '')
            if name or content:
                lines.append((f"AI实践：{name}", 2))
                if content:
                    lines.append((f"  {content}", 1))

        lines.append(("", 998))
        lines.append(("点击封面图查看完整日报", 999))

        text = "\n".join(l[0] for l in lines)
        if len(text.encode('utf-8')) <= 512:
            return text

        current = list(lines)
        while True:
            min_w = min(w for _, w in current)
            removed = False
            for i, (_, w) in enumerate(current):
                if w == min_w:
                    del current[i]
                    removed = True
                    break
            if not removed:
                break
            t = "\n".join(l[0] for l in current)
            if len(t.encode('utf-8')) <= 512:
                return t
            if len(current) <= 2:
                break

        return f"AI日报 {today_str}\n\n点击封面图查看完整日报"
    except Exception as e:
        logger.warning(f"读取摘要失败: {e}")
        return default


def upload_image_to_github(image_path):
    from src.github_uploader import upload
    return upload(image_path)


def get_access_token():
    cfg = get_wecom_config()
    if not cfg['corpid'] or not cfg['secret']:
        logger.error("WECOM_CORPID / WECOM_SECRET 未配置")
        return None
    try:
        resp = requests.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": cfg['corpid'], "corpsecret": cfg['secret']},
            timeout=10
        )
        data = resp.json()
        if data.get('errcode') == 0:
            return data['access_token']
        logger.error(f"gettoken失败: {data.get('errmsg')}")
        return None
    except Exception as e:
        logger.error(f"gettoken异常: {e}")
        return None


def _upload_media(access_token, image_path):
    try:
        url = "https://qyapi.weixin.qq.com/cgi-bin/media/upload"
        with open(image_path, 'rb') as f:
            resp = requests.post(
                url,
                params={"access_token": access_token, "type": "image"},
                files={'media': f},
                timeout=10
            )
        result = resp.json()
        if result.get('errcode') == 0:
            return result['media_id']
        logger.error(f"上传media失败: {result.get('errmsg')}")
        return None
    except Exception as e:
        logger.error(f"上传media异常: {e}")
        return None


def _send_image(access_token, media_id, touser):
    wecom = get_wecom_config()
    try:
        resp = requests.post(
            "https://qyapi.weixin.qq.com/cgi-bin/message/send",
            params={"access_token": access_token},
            json={
                "touser": touser,
                "msgtype": "image",
                "agentid": wecom['agentid'],
                "image": {"media_id": media_id},
                "safe": 0
            },
            timeout=10
        )
        result = resp.json()
        if result.get('errcode') == 0:
            invalid = result.get('invaliduser', '')
            ids = [u for u in touser.split('|') if u.strip()]
            ok = len(ids) - len([u for u in invalid.split('|') if u.strip()]) if invalid else len(ids)
            detail = f"{ok}/{len(ids)} 成功"
            if invalid:
                detail += f"，失败用户: {invalid}"
            return ok > 0, detail
        return False, result.get('errmsg', '发送失败')
    except Exception as e:
        return False, str(e)


def _send_text(access_token, content, touser):
    wecom = get_wecom_config()
    try:
        resp = requests.post(
            "https://qyapi.weixin.qq.com/cgi-bin/message/send",
            params={"access_token": access_token},
            json={
                "touser": touser,
                "msgtype": "text",
                "agentid": wecom['agentid'],
                "text": {"content": content},
                "safe": 0
            },
            timeout=10
        )
        return resp.json().get('errcode') == 0
    except Exception:
        return False


def push_via_wecom_api(image_path, touser):
    token = get_access_token()
    if not token:
        return False, "获取access_token失败"
    media_id = _upload_media(token, image_path)
    if not media_id:
        return False, "上传图片失败"
    return _send_image(token, media_id, touser)


def push_via_wecom_api_news(image_path, touser, img_url=None, github_ok=True):
    token = get_access_token()
    if not token:
        return False, "获取access_token失败"

    if not img_url:
        if not github_ok:
            return push_via_wecom_api(image_path, touser)
        ok, url = upload_image_to_github(image_path)
        if not ok:
            return push_via_wecom_api(image_path, touser)
        img_url = url

    description = get_news_summary()
    today = datetime.now().strftime('%Y-%m-%d')
    wecom = get_wecom_config()

    try:
        resp = requests.post(
            "https://qyapi.weixin.qq.com/cgi-bin/message/send",
            params={"access_token": token},
            json={
                "touser": touser,
                "msgtype": "news",
                "agentid": wecom['agentid'],
                "news": {
                    "articles": [{
                        "title": f"AI日报 {today}",
                        "description": description,
                        "url": img_url,
                        "picurl": img_url
                    }]
                },
                "safe": 0
            },
            timeout=15
        )
        result = resp.json()
        if result.get('errcode') == 0:
            invalid = result.get('invaliduser', '')
            if invalid:
                return True, f"部分成功，失败用户: {invalid}"
            return True, "成功"
        return push_via_wecom_api(image_path, touser)
    except Exception as e:
        return False, str(e)


def _push_via_webhook(webhook_key, image_path):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    try:
        with open(image_path, 'rb') as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        md5 = hashlib.md5(img_bytes).hexdigest()
        resp = requests.post(url, json={
            "msgtype": "image",
            "image": {"base64": b64, "md5": md5}
        }, timeout=30)
        return resp.json().get('errcode') == 0
    except Exception as e:
        logger.error(f"Webhook图片异常: {e}")
        return False


def send_webhook_news(webhook_key, image_path, img_url=None, github_ok=True):
    webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"

    if not img_url:
        if not github_ok:
            ok = _push_via_webhook(webhook_key, image_path)
            return ok, "纯图片（GitHub不可用降级）"
        ok, url = upload_image_to_github(image_path)
        if not ok:
            r = _push_via_webhook(webhook_key, image_path)
            return r, "纯图片（上传失败降级）"
        img_url = url

    description = get_news_summary()
    today = datetime.now().strftime('%Y-%m-%d')

    try:
        resp = requests.post(webhook_url, json={
            "msgtype": "news",
            "news": {
                "articles": [{
                    "title": f"AI日报 {today}",
                    "description": description,
                    "url": img_url,
                    "picurl": img_url
                }]
            }
        }, timeout=15)
        result = resp.json()
        if result.get('errcode') == 0:
            return True, "成功"
        return False, result.get('errmsg', '发送失败')
    except Exception as e:
        return False, str(e)


def send_webhook_text(webhook_key, content):
    try:
        resp = requests.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}",
            json={"msgtype": "text", "text": {"content": content}},
            timeout=10
        )
        return resp.json().get('errcode') == 0
    except Exception:
        return False
