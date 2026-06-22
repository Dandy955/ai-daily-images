import base64
import logging
from datetime import datetime
from pathlib import Path
import requests

from src.config import get_github_config

logger = logging.getLogger(__name__)


def upload(image_path):
    cfg = get_github_config()
    if not all([cfg['token'], cfg['owner'], cfg['repo']]):
        return False, "GitHub未配置"

    try:
        with open(image_path, 'rb') as f:
            content = f.read()

        b64 = base64.b64encode(content).decode('utf-8')
        filename = f"ai_daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/{filename}"
        headers = {
            "Authorization": "token " + cfg['token'],
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "message": f"Add {filename}",
            "content": b64,
            "branch": cfg['branch']
        }

        resp = requests.put(url, headers=headers, json=payload, timeout=30)
        result = resp.json()

        if resp.status_code in (200, 201):
            dl_url = result['content']['download_url']
            cdn_url = dl_url.replace(
                'raw.githubusercontent.com',
                'cdn.jsdelivr.net/gh'
            ).replace('/main/', '@main/')
            return True, cdn_url
        else:
            return False, result.get('message', '上传失败')

    except Exception as e:
        logger.error(f"GitHub上传异常: {e}")
        return False, str(e)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("用法: python -m src.github_uploader <图片路径>")
        sys.exit(1)
    ok, result = upload(sys.argv[1])
    print(f"{'成功' if ok else '失败'}: {result}")
