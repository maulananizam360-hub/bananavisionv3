const express = require("express");
const app = express();
const rateLimit = require("express-rate-limit");
const morgan = require("morgan");
const helmet = require("helmet");
const cors = require("cors");
const path = require("path");

const requiredEnvVars = ["DATABASE_URL", "JWT_SECRET"];
const missingEnvVars = requiredEnvVars.filter((name) => !process.env[name]);
if (missingEnvVars.length > 0) {
  throw new Error(
    `Missing required environment variables: ${missingEnvVars.join(", ")}`,
  );
}
// Ensure uploads directory exists on startup
const fs = require("fs");
const uploadDir = path.join(__dirname, "uploads");
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir, { recursive: true });
}

//routes api
const authApi = require("./src/routes/auth.routes");
const analysisApi = require("./src/routes/analysis.routes");
const diseaseApi = require("./src/routes/disease.routes");
const feedbackApi = require("./src/routes/feedback.routes");
const adminApi = require("./src/routes/admin.routes");

app.use(express.urlencoded({ extended: true, limit: "10mb" }));
app.use(express.json({ limit: "10mb" }));

// CORS harus SEBELUM helmet untuk Firebase
const defaultOrigins = [
  "http://localhost:5173",
  "http://localhost:5174",
  "http://localhost:3000",
];

const allowedOrigins = process.env.CORS_ORIGINS
  ? process.env.CORS_ORIGINS.split(",")
      .map((origin) => origin.trim())
      .filter(Boolean)
  : defaultOrigins;

const corsOptions = {
  origin: (origin, callback) => {
    if (!origin) return callback(null, true);
    if (allowedOrigins.includes(origin)) return callback(null, true);
    return callback(new Error("Not allowed by CORS"));
  },
  credentials: true,
  methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
  allowedHeaders: [
    "Content-Type",
    "Authorization",
    "Cache-Control",
    "X-Requested-With",
  ],
  optionsSuccessStatus: 204,
};

app.use(cors(corsOptions));

// Serve uploaded images statically (setelah CORS agar browser bisa akses cross-origin)
app.use("/api/uploads", express.static(path.join(__dirname, "uploads")));

app.use(
  helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: [
          "'self'",
          "'unsafe-inline'",
          "https://apis.google.com",
          "https://accounts.google.com",
          "https://*.firebase.com",
        ],
        styleSrc: ["'self'", "'unsafe-inline'"],
        imgSrc: ["'self'", "data:", "https:", "http:"],
        connectSrc: [
          "'self'",
          "https://identitytoolkit.googleapis.com",
          "https://securetoken.googleapis.com",
          "https://accounts.google.com",
          "https://*.firebaseapp.com",
        ],
        frameSrc: [
          "'self'",
          "https://accounts.google.com",
          "https://tugasakhir-7676b.firebaseapp.com",
          "https://*.firebaseapp.com",
        ],
        fontSrc: ["'self'", "data:"],
      },
    },
    crossOriginOpenerPolicy: { policy: "same-origin-allow-popups" },
    crossOriginEmbedderPolicy: false,
    crossOriginResourcePolicy: { policy: "cross-origin" },
  }),
);

if (process.env.NODE_ENV === "production" || process.env.TRUST_PROXY === "1") {
  app.set("trust proxy", 1);
}

const limiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  message: {
    code: 429,
    success: false,
    message: "Terlalu banyak permintaan, silakan coba lagi nanti.",
  },
  standardHeaders: true,
  legacyHeaders: false,
});

// General limiter applied to most routes
const generalLimiter = limiter;

// A lighter/shorter limiter for auth routes to avoid locking out users
const authLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 20, // allow more frequent short bursts for auth in development/normal use
  message: {
    code: 429,
    success: false,
    message:
      "Terlalu banyak permintaan pada endpoint auth, silakan coba lagi nanti.",
  },
  standardHeaders: true,
  legacyHeaders: false,
});

// Apply authLimiter only to auth routes
app.use("/api/auth", authLimiter);

// Apply general limiter to all other routes (skip auth to avoid blocking login flows)
app.use((req, res, next) => {
  if (req.originalUrl && (req.originalUrl.startsWith("/api/auth") || req.originalUrl.startsWith("/api/admin/login"))) return next();
  return generalLimiter(req, res, next);
});

if (process.env.NODE_ENV === "development") {
  app.use(morgan("dev"));
} else {
  app.use(morgan("combined"));
}

app.use((req, res, next) => {
  const startTime = Date.now();

  res.on("finish", () => {
    const duration = Date.now() - startTime;
    const logData = {
      timestamp: new Date().toISOString(),
      method: req.method,
      url: req.originalUrl,
      status: res.statusCode,
      duration: `${duration}ms`,
      ip: req.ip || req.connection.remoteAddress,
      userAgent: req.get("user-agent") || "unknown",
    };

    console.log(JSON.stringify(logData));

    if (
      process.env.NODE_ENV === "development" &&
      req.body &&
      Object.keys(req.body).length > 0
    ) {
      const sanitizedBody = { ...req.body };
      ["password", "token", "secret"].forEach((field) => {
        if (sanitizedBody[field]) sanitizedBody[field] = "***HIDDEN***";
      });
      console.log("Body:", JSON.stringify(sanitizedBody, null, 2));
    }
  });

  next();
});

// ── No-cache middleware for all API routes ───────────────────────────────────
// Prevents browsers and CDNs from caching API responses.
// This fixes the issue where deleted data (diseases, analyses) reappears
// on normal F5 refresh — a hard refresh (Ctrl+Shift+R) was needed before.
app.use("/api", (req, res, next) => {
  res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Expires", "0");
  res.setHeader("Surrogate-Control", "no-store");
  next();
});

// Routes
app.get("/", (req, res) =>
  res.json({
    success: true,
    message: "Hello World!",
    timestamp: new Date().toISOString(),
  }),
);

app.use("/api/auth", authApi);
app.use("/api/analyses", analysisApi);
app.use("/api/diseases", diseaseApi);
app.use("/api/feedbacks", feedbackApi);
app.use("/api/admin", adminApi);

// 404 handler
app.use((req, res, next) => {
  console.log(`404 Not Found: ${req.method} ${req.originalUrl}`);
  res.status(404).json({
    success: false,
    message: `Route ${req.method} ${req.originalUrl} not found`,
    timestamp: new Date().toISOString(),
  });
});

// Enhanced error handling middleware
app.use((err, req, res, next) => {
  console.error("Error occurred:", {
    message: err.message,
    stack: err.stack,
    url: req.originalUrl,
    method: req.method,
    body: req.body,
    params: req.params,
    timestamp: new Date().toISOString(),
  });

  // Validation Error
  if (err.name === "ValidationError") {
    return res.status(400).json({
      success: false,
      message: "Validation Error",
      errors: err.errors,
      timestamp: new Date().toISOString(),
    });
  }

  // JWT Errors
  if (err.name === "JsonWebTokenError") {
    return res.status(401).json({
      success: false,
      message: "Invalid token",
      timestamp: new Date().toISOString(),
    });
  }

  if (err.name === "TokenExpiredError") {
    return res.status(401).json({
      success: false,
      message: "Token expired",
      timestamp: new Date().toISOString(),
    });
  }

  // File upload errors
  if (err.code === "LIMIT_FILE_SIZE") {
    return res.status(413).json({
      success: false,
      message: "File too large",
      timestamp: new Date().toISOString(),
    });
  }

  // Prisma database errors
  if (err.code === "P2002") {
    return res.status(409).json({
      success: false,
      message: "Duplicate entry found",
      timestamp: new Date().toISOString(),
    });
  }

  if (err.code === "P2025") {
    return res.status(404).json({
      success: false,
      message: "Record not found",
      timestamp: new Date().toISOString(),
    });
  }

  // Syntax Error (bad JSON)
  if (err instanceof SyntaxError && err.status === 400 && "body" in err) {
    return res.status(400).json({
      success: false,
      message: "Invalid JSON format",
      timestamp: new Date().toISOString(),
    });
  }

  // Default error response
  const isDevelopment = process.env.NODE_ENV === "development";

  res.status(err.statusCode || 500).json({
    success: false,
    message: err.message || "Internal server error",
    ...(isDevelopment && {
      stack: err.stack,
      details: err.details || "No additional details",
    }),
    timestamp: new Date().toISOString(),
  });
});

// Global exception handlers
process.on("uncaughtException", (err) => {
  console.error("Uncaught Exception:", {
    message: err.message,
    stack: err.stack,
    timestamp: new Date().toISOString(),
  });
  process.exit(1);
});

process.on("unhandledRejection", (reason, promise) => {
  console.error("Unhandled Rejection:", {
    promise: promise,
    reason: reason,
    timestamp: new Date().toISOString(),
  });
  process.exit(1);
});

module.exports = app;
