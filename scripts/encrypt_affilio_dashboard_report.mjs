import { createCipheriv, randomBytes, scryptSync } from "node:crypto";
import { readFile, writeFile, rm } from "node:fs/promises";

const inputPath = "affilio-dashboard-diagnostic.json";
const outputPath = "affilio-dashboard-diagnostic.enc.json";
const passphrase = process.env.AFFILIO_PASS || "";
if (!passphrase) throw new Error("AFFILIO_PASS_required_for_report_encryption");

let plaintext;
try {
  plaintext = await readFile(inputPath);
} catch {
  throw new Error("diagnostic_report_missing");
}
const salt = randomBytes(16);
const iv = randomBytes(12);
const key = scryptSync(passphrase, salt, 32, { N: 32768, r: 8, p: 1, maxmem: 96 * 1024 * 1024 });
const cipher = createCipheriv("aes-256-gcm", key, iv);
const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
const payload = {
  version: 1,
  algorithm: "AES-256-GCM",
  kdf: "scrypt-N32768-r8-p1",
  salt: salt.toString("base64"),
  iv: iv.toString("base64"),
  tag: cipher.getAuthTag().toString("base64"),
  ciphertext: ciphertext.toString("base64")
};
await writeFile(outputPath, JSON.stringify(payload));
await rm(inputPath, { force: true });
console.log("AFFILIO_REPORT_ENCRYPTED=true");
