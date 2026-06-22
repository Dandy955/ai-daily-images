import os
import json
from pathlib import Path
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_DIR / 'config'

load_dotenv(PROJECT_DIR / '03-本地推送服务' / '.env')

def _env(key, default=''):
    return os.environ.get(key, default)


def load_push_config(test_mode=False):
    filename = 'push_settings.test.json' if test_mode else 'push_settings.json'
    path = CONFIG_DIR / filename
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config


def get_user_id_name_map(config):
    raw = config.get('企微用户映射', {})
    return {k: v for k, v in raw.items() if not k.startswith('_')}


def get_github_config():
    return {
        'token': _env('GITHUB_TOKEN', ''),
        'owner': _env('GITHUB_OWNER', ''),
        'repo': _env('GITHUB_REPO', ''),
        'branch': _env('GITHUB_BRANCH', 'main'),
    }


def get_wecom_config():
    return {
        'corpid': _env('WECOM_CORPID', ''),
        'agentid': _env('WECOM_AGENTID', ''),
        'secret': _env('WECOM_SECRET', ''),
        'webhook_key': _env('WECOM_WEBHOOK_KEY', ''),
    }


def get_email_config():
    return {
        'host': _env('SMTP_HOST', 'smtp.qq.com'),
        'port': int(_env('SMTP_PORT', '465')),
        'user': _env('SMTP_USER', ''),
        'password': _env('SMTP_PASSWORD', ''),
        'sender_name': _env('SENDER_NAME', 'GESC AI知识学习与应用服务组'),
    }


def get_feedback_config():
    return {
        'wecom_user': _env('FEEDBACK_WECOM_USER', '01005598'),
        'email': _env('FEEDBACK_EMAIL', 'lix625@onewo.com'),
    }
