"""Web Push（VAPID）发送。

第一次运行时在 connector/data/ 生成 VAPID 密钥对。推送由电脑直接发到
手机浏览器厂商的推送服务（iPhone 是 Apple），不需要自建服务器，但电脑要能上网。
"""

from __future__ import annotations

import base64
import json
import threading
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # 没装 pywebpush 时只做实时通讯，不发锁屏推送
    webpush = None
    WebPushException = Exception

VAPID_CONTACT = "mailto:standby-salvage@localhost"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class PushSender:
    def __init__(self, data_dir: Path) -> None:
        self.key_file = data_dir / "vapid_private.pem"
        if not self.key_file.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            self.key_file.write_bytes(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ))
        key = serialization.load_pem_private_key(self.key_file.read_bytes(), password=None)
        raw_pub = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.public_key = _b64url(raw_pub)

    def send_all(self, devices: dict, title: str, body: str, approval_id: str | None) -> None:
        if webpush is None:
            return
        payload = json.dumps({"title": title, "body": body, "approvalId": approval_id},
                             ensure_ascii=False)
        for dev in devices.values():
            sub = dev.get("push")
            if sub:
                # 网络请求放到后台线程，不阻塞连接程序
                threading.Thread(target=self._send, args=(dev, sub, payload), daemon=True).start()

    def _send(self, dev: dict, sub: dict, payload: str) -> None:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=str(self.key_file),
                vapid_claims={"sub": VAPID_CONTACT},
                ttl=3600,
                headers={"Urgency": "high"},
            )
        except WebPushException as exc:
            print(f"[推送] 发给 {dev.get('id')} 失败：{exc}")
