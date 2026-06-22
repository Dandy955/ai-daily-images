import ssl
import smtplib
import logging
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.header import Header
from email.utils import formataddr

from src.config import get_email_config, PROJECT_DIR

logger = logging.getLogger(__name__)


def get_email_news_summary():
    today_str = datetime.now().strftime('%Y%m%d')
    summary_path = PROJECT_DIR / '04-AI日报' / f'AI日报_{today_str}_summary.json'
    default = f"AI日报 {today_str}\n\n详情请查看附件图片"

    try:
        if not summary_path.exists():
            return default
        with open(summary_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        parts = []
        today = datetime.now().strftime('%Y-%m-%d')
        parts.append(f"{'='*50}")
        parts.append(f"AI日报 {today}")
        parts.append(f"{'='*50}\n")

        img_news = data.get('img_news', [])
        if img_news:
            parts.append("【AI要闻】")
            for i, news in enumerate(img_news[:3], 1):
                title = news if isinstance(news, str) else news.get('title', '')
                parts.append(f"  {i}. {title}")
            parts.append("")

        tool = data.get('tool', {})
        if tool:
            parts.append(f"【AI工具：{tool.get('name', '')}】")
            scene = tool.get('scene', '')
            if scene:
                parts.append(f"  场景：{scene}")
            parts.append("")

        case = data.get('case', {})
        if case:
            parts.append(f"【AI实践：{case.get('name', '')}】")
            content = case.get('content', '')
            if content:
                parts.append(f"  {content}")
            parts.append("")

        parts.append(f"{'='*50}")
        parts.append("详情请查看附件图片")
        return "\n".join(parts)
    except Exception:
        return default


def send_email_with_news_summary(image_path, to_addr, subject=None):
    cfg = get_email_config()
    if not cfg['password'] or not cfg['user']:
        logger.error("SMTP 未配置")
        return False

    summary = get_email_news_summary()
    if subject is None:
        subject = f"AI日报 {datetime.now().strftime('%Y-%m-%d')}"

    msg = MIMEMultipart('mixed')
    msg['From'] = formataddr((str(Header(cfg['sender_name'], 'utf-8')), cfg['user']))
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg.attach(MIMEText(summary, 'plain', 'utf-8'))

    with open(image_path, 'rb') as f:
        attachment = MIMEImage(f.read())
    attachment.add_header('Content-Disposition', 'attachment', filename=Path(image_path).name)
    msg.attach(attachment)

    try:
        with smtplib.SMTP_SSL(cfg['host'], cfg['port'], context=ssl.create_default_context()) as server:
            server.login(cfg['user'], cfg['password'])
            server.sendmail(cfg['user'], to_addr, msg.as_string())
        logger.info(f"邮件发送成功: {to_addr}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


def send_simple_email(to_addr, subject, content):
    cfg = get_email_config()
    if not cfg['password'] or not cfg['user']:
        return False

    msg = MIMEMultipart()
    msg['From'] = formataddr((str(Header(cfg['sender_name'], 'utf-8')), cfg['user']))
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL(cfg['host'], cfg['port'], context=ssl.create_default_context()) as server:
            server.login(cfg['user'], cfg['password'])
            server.sendmail(cfg['user'], to_addr, msg.as_string())
        return True
    except Exception:
        return False


import json  # noqa: E402 (needed by get_email_news_summary)
