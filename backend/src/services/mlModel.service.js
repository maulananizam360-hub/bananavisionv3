const MlModelModel = require("../models/mlModelModel");
const axios = require("axios");
const path = require("path");
const fs = require("fs");
const {
  getModelStorageDir,
  confirmModelSaved,
  deleteModelFile,
} = require("../utils/localModelStorage");
const {
  isConfigured: isCloudStorageConfigured,
  uploadModel,
  createModelSignedUrl,
  deleteModel: deleteCloudModel,
} = require("../utils/supabaseStorage");

const ML_SERVER_URL = (
  process.env.ML_SERVER_URL || "http://localhost:8000"
).replace(/\/$/, "");

class MlModelService {
  static async getModels() {
    try {
      let activePyModel = null;
      try {
        const response = await axios.get(`${ML_SERVER_URL}/api/models`, {
          headers: {
            Authorization: `Bearer ${process.env.MODEL_SYNC_TOKEN || ""}`,
          },
        });
        if (response.data && response.data.success) {
          activePyModel = response.data.active_model;
        }
      } catch (err) {
        console.error("Failed to reach Python ML server /api/models:", err.message);
      }

      const dbModels = await MlModelModel.findAll();

      if (activePyModel) {
        if (activePyModel.filename) {
          const activeDbModel = dbModels.find((m) => m.filename === activePyModel.filename);
          if (activeDbModel && !activeDbModel.isActive) {
            await MlModelModel.update(activeDbModel.id, { isActive: true });
            await MlModelModel.deactivateAllExcept(activeDbModel.id);
            return await MlModelModel.findAll();
          }
        } else {
          const activeDbModel = dbModels.find((m) => m.isActive);
          if (activeDbModel) {
            await MlModelModel.deactivateAllExcept(null);
            return await MlModelModel.findAll();
          }
        }
      }

      return dbModels;
    } catch (error) {
      throw error;
    }
  }

  static async activateModel(id) {
    const model = await MlModelModel.findById(id);
    if (!model) {
      throw new Error("Model tidak ditemukan di database");
    }

    const modelStorageDir = getModelStorageDir();
    const modelPath = path.join(modelStorageDir, model.filename);

    if (!isCloudStorageConfigured && !fs.existsSync(modelPath)) {
      throw new Error(
        `File model '${model.filename}' tidak ditemukan di direktori penyimpanan server: ${modelStorageDir}. ` +
          `Pastikan model sudah diunggah dengan benar.`
      );
    }

    try {
      const modelUrl = isCloudStorageConfigured
        ? await createModelSignedUrl(model.filename)
        : null;
      console.log(`Sending reload request to ${ML_SERVER_URL}/api/reload for ${model.filename}...`);
      const response = await axios.post(`${ML_SERVER_URL}/api/reload`, {
        filename: model.filename,
        model_type: model.modelType === "custom" ? "mobilenetv2" : model.modelType,
        url: modelUrl,
      }, {
        headers: {
          Authorization: `Bearer ${process.env.MODEL_SYNC_TOKEN || ""}`,
        },
      });

      if (!response.data || !response.data.success) {
        throw new Error(response.data.message || "Gagal memuat model di server Python");
      }
    } catch (err) {
      const errMsg =
        err.response && err.response.data && err.response.data.detail
          ? err.response.data.detail
          : err.message;
      throw new Error(`Koneksi ke AI server gagal atau gagal memuat model: ${errMsg}`);
    }

    const updated = await MlModelModel.update(id, { isActive: true });
    await MlModelModel.deactivateAllExcept(id);

    return updated;
  }

  static async storeUploadedModel(filePath, filename) {
    if (isCloudStorageConfigured) {
      await uploadModel(filePath, filename);
      return;
    }

    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "Model AI di Railway memerlukan Supabase Storage. Konfigurasikan SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY."
      );
    }

    confirmModelSaved(filePath, filename);
  }

  static async getActiveModelInfo() {
    const model = await this.getActiveModel();
    if (!model) return null;

    return {
      filename: model.filename,
      modelType: model.modelType,
      url: isCloudStorageConfigured
        ? await createModelSignedUrl(model.filename)
        : null,
    };
  }

  static async registerUploadedModel(name, filename, modelType, fileSize) {
    const existing = await MlModelModel.findByFilename(filename);
    if (existing) {
      return await MlModelModel.update(existing.id, {
        name,
        modelType,
        fileSize,
        updatedAt: new Date(),
      });
    }

    return await MlModelModel.create({
      name,
      filename,
      modelType,
      isActive: false,
      fileSize,
    });
  }

  static async deleteModel(id) {
    const model = await MlModelModel.findById(id);
    if (!model) {
      throw new Error("Model tidak ditemukan");
    }

    if (isCloudStorageConfigured) {
      await deleteCloudModel(model.filename);
    }
    deleteModelFile(model.filename);

    return await MlModelModel.delete(id);
  }

  static async getHealth() {
    try {
      const response = await axios.get(`${ML_SERVER_URL}/health`);
      return {
        online: true,
        details: response.data,
      };
    } catch (err) {
      return {
        online: false,
        message: err.message,
      };
    }
  }

  static async getActiveModel() {
    const models = await MlModelModel.findAll();
    return models.find((m) => m.isActive) || null;
  }
}

module.exports = MlModelService;
