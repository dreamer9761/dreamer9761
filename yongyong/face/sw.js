// 휴대폰에 '앱'으로 설치되게 하는 최소 서비스 워커 (오프라인 저장은 하지 않음: 항상 맥미니의 최신 화면)
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
