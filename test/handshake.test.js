import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { ADB_CMDS, ADB_VERSION, ADB_DEFAULT_MAXDATA } from '../src/adb/constants.js';
import { decodePacket } from '../src/adb/packet.js';
import { AdbDeviceConnection, buildHostConnectPacket } from '../src/adb/handshake.js';

const propsPath = path.resolve(process.cwd(), 'prop.json');

function parseBannerFeatures(banner) {
  const m = banner.match(/features=([^;]+)/);
  return m ? m[1].split(',').filter(Boolean) : [];
}

test('device handshake responds to host CNXN and negotiates features', () => {
  const hostFeatures = ['shell_v2', 'cmd', 'stat_v2', 'foobar'];
  const hostPkt = buildHostConnectPacket({ version: ADB_VERSION, maxData: 8192, features: hostFeatures });

  const device = new AdbDeviceConnection({ propsPath, version: ADB_VERSION, maxData: ADB_DEFAULT_MAXDATA });
  const resp = device.handleConnect(hostPkt);

  const decoded = decodePacket(resp);
  assert.equal(decoded.command, ADB_CMDS.CNXN);
  const devVersion = decoded.arg0 >>> 0;
  const devMax = decoded.arg1 >>> 0;
  assert.equal(devVersion, ADB_VERSION);
  assert.equal(devMax, ADB_DEFAULT_MAXDATA); // min(4096, 8192)

  const banner = decoded.payload.toString('utf8');
  assert.ok(banner.startsWith('device:'));
  assert.match(banner, /ro.product.name=test_product;/);
  assert.match(banner, /ro.product.model=Test Model;/);
  assert.match(banner, /ro.product.device=test_device;/);

  // Negotiated features = intersection
  const feats = parseBannerFeatures(banner);
  assert.deepEqual(feats.sort(), ['cmd', 'shell_v2', 'stat_v2'].sort());

  // Connection state updated
  assert.equal(device.connected, true);
  assert.equal(device.maxData, ADB_DEFAULT_MAXDATA);
});
