const express = require("express");
const router = express.Router();
const AdminController = require("../controllers/admin.controller");
const AdminDiseaseController = require("../controllers/adminDisease.controller");
const MlModelController = require("../controllers/mlModel.controller");
const { authenticateAdmin } = require("../middleware/adminAuth");
const { getModelStorageDir, ensureModelDir } = require("../utils/localModelStorage");
const multer = require("multer");
const path = require("path");
const fs = require("fs");

const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    const dest = ensureModelDir();
    cb(null, dest);
  },
  filename: function (req, file, cb) {
    const ext = path.extname(file.originalname).toLowerCase();
    if (ext !== ".keras") {
      return cb(new Error("Hanya file model dengan ekstensi .keras yang diperbolehkan"));
    }
    const safeName = path.basename(file.originalname);
    cb(null, safeName);
  },
});

const upload = multer({
  storage: storage,
  limits: { fileSize: 500 * 1024 * 1024 },
});

// Admin auth
router.post("/login", AdminController.login);
router.get("/profile", authenticateAdmin, AdminController.getProfile);
router.get("/stats", authenticateAdmin, AdminController.getDashboardStats);

// Disease CRUD
router.get("/diseases", authenticateAdmin, AdminDiseaseController.getDiseases);
router.post("/diseases", authenticateAdmin, AdminDiseaseController.createDisease);
router.put("/diseases/:id", authenticateAdmin, AdminDiseaseController.updateDisease);
router.delete("/diseases/:id", authenticateAdmin, AdminDiseaseController.deleteDisease);
router.put("/diseases/:id/toggle", authenticateAdmin, AdminDiseaseController.toggleActive);

// ML Model Management
router.get("/models", authenticateAdmin, MlModelController.getModels);
router.get("/models/health", authenticateAdmin, MlModelController.getHealth);
router.post(
  "/models/upload",
  authenticateAdmin,
  upload.single("modelFile"),
  MlModelController.uploadModel
);
router.put("/models/:id/activate", authenticateAdmin, MlModelController.activateModel);
router.delete("/models/:id", authenticateAdmin, MlModelController.deleteModel);

// Endpoint untuk diakses Python server saat startup
router.get("/models/active-info", (req, res, next) => {
  const syncToken = process.env.MODEL_SYNC_TOKEN;
  if (!syncToken && process.env.NODE_ENV !== "production") return next();
  if (!syncToken) {
    return res.status(503).json({ success: false, message: "MODEL_SYNC_TOKEN belum dikonfigurasi" });
  }
  if (req.get("authorization") !== `Bearer ${syncToken}`) {
    return res.status(401).json({ success: false, message: "Unauthorized" });
  }
  return next();
}, MlModelController.getActiveModelInfo);

module.exports = router;
