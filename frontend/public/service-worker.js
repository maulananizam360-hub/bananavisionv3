const CACHE_NAME = "bananavision-v2";
const OFFLINE_URL = "/offline.html";

// Only cache known root-level assets here. Avoid hardcoding Vite build asset names.
const urlsToCache = ["/", OFFLINE_URL];

self.addEventListener("install", (event) => {
  console.log("[ServiceWorker] Install");
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      try {
        // addAll will fail if any request fails — add individually so failures don't break install
        for (const url of urlsToCache) {
          try {
            await cache.add(url);
          } catch (err) {
            console.warn("[ServiceWorker] Failed to cache", url, err);
          }
        }
      } catch (err) {
        console.error("[ServiceWorker] Error during caching", err);
      }
    })
  );
});

self.addEventListener("activate", (event) => {
  console.log("[ServiceWorker] Activate");
  event.waitUntil(
    caches.keys().then((keyList) =>
      Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            console.log("[ServiceWorker] Removing old cache", key);
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Only handle GET requests
  if (event.request.method !== "GET") return;
  if (new URL(event.request.url).origin !== self.location.origin) return;

  event.respondWith(
    caches.match(event.request).then((response) => {
      if (response) {
        return response;
      }
      return fetch(event.request)
        .then((networkResponse) => {
          // Optionally cache new requests (runtime caching)
          return caches.open(CACHE_NAME).then((cache) => {
            try {
              // Only cache same-origin requests
              if (event.request.url.startsWith(self.location.origin)) {
                cache.put(event.request, networkResponse.clone());
              }
            } catch (err) {
              console.warn(
                "[ServiceWorker] Failed to cache runtime request",
                err
              );
            }
            return networkResponse;
          });
        })
        .catch(() =>
          event.request.mode === "navigate"
            ? caches.match(OFFLINE_URL)
            : Response.error()
        );
    })
  );
});
