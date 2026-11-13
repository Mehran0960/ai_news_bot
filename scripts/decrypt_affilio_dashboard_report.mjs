import { createDecipheriv, scryptSync } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

const inputPath = process.argv[2] || "affilio-dashboard-diagnostic.enc.json";
const outputPath = process.argv[3] || "affilio-dashboard-diagnostic.json";
const passphrase = process.env.AFFILIO_PASS || "";
if (!passphrase) throw new Error("Set AFFILIO_PASS in your local environment first.");

const payload = JSON.parse(await readFile(inputPath, "utf8"));
if (payload.version !== 1 || payload.algorithm !== "AES-256-GCM") {
  throw new Error("Unsupported encrypted report format.");
}
const salt = Buffer.from(payload.salt, "base64");
const iv = Buffer.from(payload.iv, "base64");
const tag = Buffer.from(payload.tag, "base64");
const ciphertext = Buffer.from(payload.ciphertext, "base64");
const key = scryptSync(passphrase, salt, 32, { N: 32768, r: 8, p: 1, maxmem: 96 * 1024 * 1024 });
const decipher = createDecipheriv("aes-256-gcm", key, iv);
decipher.setAuthTag(tag);
const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
await writeFile(outputPath, plaintext, { mode: 0o600 });
console.log("Decrypted report written to " + outputPath + " (keep it private).");
