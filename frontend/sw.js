// Service worker : garde les pages en cache pour un affichage rapide,
// mais ne met jamais en cache les données de l'API (toujours en direct).
const CACHE = "timdeiz-v2";
const FILES = [
    "index.html", "admin.html", "client.html", "style.css",
    "app.js", "account.js", "admin.js", "client.js", "icons/logo.jpg",
];

self.addEventListener("install", event => {
    event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)));
    self.skipWaiting();
});

self.addEventListener("activate", event => {
    event.waitUntil(caches.keys().then(keys =>
        Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))));
    self.clients.claim();
});

self.addEventListener("fetch", event => {
    const url = new URL(event.request.url);
    if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) return;

    // Réseau d'abord, cache en secours si le serveur ne répond pas
    event.respondWith(
        fetch(event.request)
            .then(response => {
                const copy = response.clone();
                caches.open(CACHE).then(cache => cache.put(event.request, copy));
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
