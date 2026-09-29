const fs = require("fs");
const tus = require("tus-js-client");
const { client, bucket, isConfigured } = require("../../config/supabase");

function requireStorage() {
	if (!isConfigured) {
		throw new Error(
			"Supabase Storage belum dikonfigurasi. Isi SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY."
		);
	}
}

async function uploadModel(filePath, filename) {
	requireStorage();
	const fileSize = (await fs.promises.stat(filePath)).size;
	const projectRef = new URL(process.env.SUPABASE_URL).hostname.split(".")[0];
	const endpoint = `https://${projectRef}.storage.supabase.co/storage/v1/upload/resumable`;

	await new Promise((resolve, reject) => {
		const upload = new tus.Upload(fs.createReadStream(filePath), {
			endpoint,
			headers: {
				authorization: `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
				apikey: process.env.SUPABASE_SERVICE_ROLE_KEY,
				"x-upsert": "true",
			},
			metadata: {
				bucketName: bucket,
				objectName: filename,
				contentType: "application/octet-stream",
				cacheControl: "3600",
			},
			uploadSize: fileSize,
			chunkSize: 6 * 1024 * 1024,
			uploadDataDuringCreation: true,
			removeFingerprintOnSuccess: true,
			retryDelays: [0, 3000, 5000, 10000, 20000],
			onError: reject,
			onSuccess: resolve,
		});

		upload.start();
	});
}

async function createModelSignedUrl(filename) {
	requireStorage();
	const { data, error } = await client.storage
		.from(bucket)
		.createSignedUrl(filename, 60 * 60 * 24);
	if (error) throw error;
	return data.signedUrl;
}

async function deleteModel(filename) {
	requireStorage();
	const { error } = await client.storage.from(bucket).remove([filename]);
	if (error) throw error;
}

module.exports = {
	isConfigured,
	uploadModel,
	createModelSignedUrl,
	deleteModel,
};
