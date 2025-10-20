import { ADB_DEFAULT_MAXDATA } from './constants.js';

// Computes the ADB data checksum (sum of all payload bytes modulo 2^32)
export function computeChecksum(payload) {
  if (!payload || payload.length === 0) return 0;
  let sum = 0 >>> 0;
  for (let i = 0; i < payload.length; i++) {
    sum = (sum + (payload[i] & 0xff)) >>> 0;
  }
  return sum >>> 0;
}

// Encodes a 24-byte ADB packet header + payload buffer
export function encodePacket({ command, arg0 = 0, arg1 = 0, payload = Buffer.alloc(0) }) {
  if (!Buffer.isBuffer(payload)) payload = Buffer.from(payload);
  const header = Buffer.alloc(24);

  const length = payload.length >>> 0;
  const checksum = computeChecksum(payload) >>> 0;
  const magic = (command ^ 0xffffffff) >>> 0;

  header.writeUInt32LE(command >>> 0, 0);
  header.writeUInt32LE(arg0 >>> 0, 4);
  header.writeUInt32LE(arg1 >>> 0, 8);
  header.writeUInt32LE(length, 12);
  header.writeUInt32LE(checksum, 16);
  header.writeUInt32LE(magic, 20);

  return Buffer.concat([header, payload]);
}

// Decodes an ADB packet buffer (must contain header + complete payload)
export function decodePacket(buffer) {
  if (!Buffer.isBuffer(buffer)) buffer = Buffer.from(buffer);
  if (buffer.length < 24) throw new Error('Buffer too small for ADB header');

  const command = buffer.readUInt32LE(0) >>> 0;
  const arg0 = buffer.readUInt32LE(4) >>> 0;
  const arg1 = buffer.readUInt32LE(8) >>> 0;
  const data_length = buffer.readUInt32LE(12) >>> 0;
  const data_checksum = buffer.readUInt32LE(16) >>> 0;
  const magic = buffer.readUInt32LE(20) >>> 0;

  if (((command ^ 0xffffffff) >>> 0) !== magic) {
    throw new Error('Invalid ADB packet magic');
  }

  const expectedTotal = 24 + data_length;
  if (buffer.length < expectedTotal) {
    throw new Error('Incomplete ADB packet: missing payload bytes');
  }

  const payload = buffer.slice(24, 24 + data_length);
  const actualChecksum = computeChecksum(payload);
  if ((actualChecksum >>> 0) !== (data_checksum >>> 0)) {
    throw new Error('Invalid ADB payload checksum');
  }

  return {
    command,
    arg0,
    arg1,
    data_length,
    data_checksum,
    magic,
    payload
  };
}

export function maxDataOrDefault(maxData) {
  return (typeof maxData === 'number' && maxData > 0) ? maxData : ADB_DEFAULT_MAXDATA;
}
