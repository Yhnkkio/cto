import test from 'node:test';
import assert from 'node:assert/strict';
import { ADB_CMDS, commandToString } from '../src/adb/constants.js';
import { encodePacket, decodePacket, computeChecksum } from '../src/adb/packet.js';

function makePayload(str) {
  return Buffer.from(str, 'utf8');
}

test('encode/decode roundtrip validates checksum and magic', () => {
  const payload = makePayload('Hello, ADB!');
  const buf = encodePacket({ command: ADB_CMDS.WRTE, arg0: 123, arg1: 456, payload });

  const decoded = decodePacket(buf);
  assert.equal(decoded.command, ADB_CMDS.WRTE);
  assert.equal(decoded.arg0, 123);
  assert.equal(decoded.arg1, 456);
  assert.equal(decoded.data_length, payload.length);
  assert.equal(decoded.data_checksum >>> 0, computeChecksum(payload) >>> 0);
  assert.equal(decoded.magic >>> 0, (ADB_CMDS.WRTE ^ 0xffffffff) >>> 0);
  assert.equal(decoded.payload.toString('utf8'), 'Hello, ADB!');
});

test('decode detects invalid magic', () => {
  const payload = makePayload('abc');
  const buf = encodePacket({ command: ADB_CMDS.OKAY, arg0: 1, arg1: 2, payload });
  // Corrupt magic
  buf.writeUInt32LE(0xdeadbeef, 20);
  assert.throws(() => decodePacket(buf), /Invalid ADB packet magic/);
});

test('decode detects invalid checksum', () => {
  const payload = makePayload('checksum');
  const buf = encodePacket({ command: ADB_CMDS.OPEN, arg0: 0, arg1: 0, payload });
  // Corrupt a payload byte
  buf[24] ^= 0xff;
  assert.throws(() => decodePacket(buf), /Invalid ADB payload checksum/);
});

test('commandToString maps known commands', () => {
  assert.equal(commandToString(ADB_CMDS.CNXN), 'CNXN');
});
