const { createClient } = require("@supabase/supabase-js");

const url = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const client = url && serviceRoleKey ? createClient(url, serviceRoleKey) : null;

module.exports = {
	client,
	bucket: process.env.SUPABASE_BUCKET || "models",
	isConfigured: Boolean(client),
};
