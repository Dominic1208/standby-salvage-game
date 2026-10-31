// Service Worker：只负责锁屏推送和点击通知后打开对应请求。
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch {}
  const title = data.title || "待机回收站";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    tag: data.approvalId || undefined,   // 同一请求的提醒合并为一条
    renotify: true,
    data: { approvalId: data.approvalId || null },
    icon: "/icon-192.png",
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const id = event.notification.data?.approvalId;
  const url = id ? `/?approval=${encodeURIComponent(id)}` : "/";
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) {
      await c.focus();
      if (id) c.postMessage({ type: "open-approval", id });
      return;
    }
    await self.clients.openWindow(url);
  })());
});
