import { test } from "node:test";
import assert from "node:assert/strict";
import QRCode from "qrcode";
import {
  BinaryBitmap,
  HybridBinarizer,
  QRCodeReader,
  RGBLuminanceSource,
} from "@zxing/library";
import { isActivityQrCode } from "./qrScanner";

/** Render actual QR pixels, then run the same decoder used by the camera. */
function decodeQr(payload: string) {
  const { modules } = QRCode.create(payload, { errorCorrectionLevel: "M" });
  const margin = 4,
    scale = 8,
    width = (modules.size + margin * 2) * scale;
  const pixels = new Uint8ClampedArray(width * width).fill(255);
  for (let y = 0; y < modules.size; y++)
    for (let x = 0; x < modules.size; x++)
      if (modules.get(y, x))
        for (let dy = 0; dy < scale; dy++)
          for (let dx = 0; dx < scale; dx++)
            pixels[
              ((y + margin) * scale + dy) * width + (x + margin) * scale + dx
            ] = 0;
  const bitmap = new BinaryBitmap(
    new HybridBinarizer(new RGBLuminanceSource(pixels, width, width)),
  );
  return new QRCodeReader().decode(bitmap).getText();
}

test("activity QR pixels round-trip through the production decoder", () => {
  for (const token of ["A".repeat(43), "_-".repeat(21) + "Z"])
    assert.equal(
      decodeQr(`ochakovo:activity:v1:${token}`),
      `ochakovo:activity:v1:${token}`,
    );
});

test("decoding a foreign URL does not make it an accepted activity", () => {
  const decoded = decodeQr("https://example.com/foreign-qr");
  assert.equal(isActivityQrCode(decoded), false);
});
