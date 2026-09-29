const rawBaseUrl = import.meta.env.VITE_API_BASE_URL;

// Fallback hanya dipakai saat development lokal dan VITE_API_BASE_URL tidak di-set
const DEFAULT_BASE_URL = "https://bananavisionv3-production-12ee.up.railway.app/api"; // Ganti dengan URL default yang sesuai

let _warnedMissingUrl = false;

const BASE_URL = rawBaseUrl
  ? rawBaseUrl.replace(/\/+$/, "")
  : (() => {
      if (!_warnedMissingUrl) {
        console.warn(
          `[BananaVision] VITE_API_BASE_URL is not defined. Falling back to ${DEFAULT_BASE_URL}.`
        );
        _warnedMissingUrl = true;
      }
      return DEFAULT_BASE_URL;
    })();

export default BASE_URL;
