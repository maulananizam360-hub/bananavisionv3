const MlModelService = require("../services/mlModel.service");
const { successResponse, errorResponse } = require("../utils/response");
const fs = require("fs");
const path = require("path");

class MlModelController {
  static async getModels(req, res) {
    try {
      const models = await MlModelService.getModels();
      return successResponse(res, models, "Berhasil mengambil data model ML");
    } catch (error) {
      console.error("Error get models:", error.message);
      return errorResponse(res, error.message || "Gagal mengambil data model", 500);
    }
  }

  static async activateModel(req, res) {
    try {
      const { id } = req.params;
      const updated = await MlModelService.activateModel(id);
      return successResponse(res, updated, `Model '${updated.name}' berhasil diaktifkan`);
    } catch (error) {
      console.error("Error activate model:", error.message);
      return errorResponse(res, error.message || "Gagal mengaktifkan model", 500);
    }
  }

  static async uploadModel(req, res) {
    try {
      if (!req.file) {
        return errorResponse(res, "Tidak ada file model .keras yang diunggah", 400);
      }

      const { name, modelType } = req.body;
      if (!name || !modelType) {
        if (req.file.path && fs.existsSync(req.file.path)) {
          fs.unlinkSync(req.file.path);
        }
        return errorResponse(res, "Field name dan modelType wajib diisi", 400);
      }

      const filename = req.file.filename;
      const fileSize = req.file.size;

      console.log(`Model file saved to server storage: ${req.file.path} (${fileSize} bytes)`);
      await MlModelService.storeUploadedModel(req.file.path, filename);
      if (fs.existsSync(req.file.path)) {
        fs.unlinkSync(req.file.path);
      }

      const registered = await MlModelService.registerUploadedModel(
        name,
        filename,
        modelType,
        fileSize
      );

      let autoActivated = false;
      try {
        const currentActive = await MlModelService.getActiveModel();
        if (!currentActive) {
          console.log(`No active model found — auto-activating '${filename}'...`);
          await MlModelService.activateModel(registered.id);
          autoActivated = true;
          console.log(`Auto-activated: ${filename}`);
        }
      } catch (activateErr) {
        console.warn(`Auto-activation failed (non-fatal): ${activateErr.message}`);
      }

      const message = autoActivated
        ? "Model berhasil diunggah ke server dan otomatis diaktifkan"
        : "Model berhasil diunggah ke server dan didaftarkan";

      return successResponse(res, registered, message, 201);
    } catch (error) {
      if (req.file && req.file.path && fs.existsSync(req.file.path)) {
        try {
          fs.unlinkSync(req.file.path);
        } catch (_) {}
      }
      console.error("Error upload model:", error.message);
      return errorResponse(res, error.message || "Gagal mengunggah model", 500);
    }
  }

  static async deleteModel(req, res) {
    try {
      const { id } = req.params;
      await MlModelService.deleteModel(id);
      return successResponse(res, null, "Model berhasil dihapus");
    } catch (error) {
      console.error("Error delete model:", error.message);
      return errorResponse(res, error.message || "Gagal menghapus model", 500);
    }
  }

  static async getHealth(req, res) {
    try {
      const health = await MlModelService.getHealth();
      return successResponse(res, health, "Berhasil mengecek status server AI");
    } catch (error) {
      console.error("Error check AI server health:", error.message);
      return errorResponse(res, error.message || "Gagal mengecek status server AI", 500);
    }
  }

  static async getActiveModelInfo(req, res) {
    try {
      const activeModel = await MlModelService.getActiveModelInfo();
      if (!activeModel) {
        return successResponse(res, null, "Tidak ada model aktif");
      }

      return successResponse(res, activeModel, "Model aktif ditemukan");
    } catch (error) {
      console.error("Error getActiveModelInfo:", error.message);
      return errorResponse(res, error.message || "Gagal mengambil info model aktif", 500);
    }
  }
}

module.exports = MlModelController;
