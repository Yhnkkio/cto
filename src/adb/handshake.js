import fs from 'node:fs';
import path from 'node:path';
import { ADB_CMDS, ADB_VERSION, ADB_DEFAULT_MAXDATA } from './constants.js';
import { encodePacket, maxDataOrDefault } from './packet.js';

function parseFeaturesFromHostBanner(banner) {
  // host banner usually like: 'host::features=feature1,feature2,...'
  const idx = banner.indexOf('features=');
  if (idx === -1) return [];
  const after = banner.slice(idx + 'features='.length);
  const end = after.indexOf('\0');
  const featStr = (end !== -1 ? after.slice(0, end) : after).replace(/;.*$/, '');
  if (!featStr) return [];
  return featStr.split(',').map((s) => s.trim()).filter(Boolean);
}

function buildDeviceBanner({ serial, props, features }) {
  const model = props['ro.product.model'] || 'unknown';
  const name = props['ro.product.name'] || 'unknown';
  const device = props['ro.product.device'] || 'unknown';
  const featureStr = features && features.length ? `features=${features.join(',')};` : '';
  const serialSegment = serial ? `device:${serial}:` : 'device::';
  return `${serialSegment}ro.product.name=${name};ro.product.model=${model};ro.product.device=${device};${featureStr}`;
}

export class AdbDeviceConnection {
  constructor({ propsPath = path.resolve(process.cwd(), 'prop.json'), version = ADB_VERSION, maxData = ADB_DEFAULT_MAXDATA } = {}) {
    this.propsPath = propsPath;
    this.version = version >>> 0;
    this.maxData = maxDataOrDefault(maxData) >>> 0;
    this.connected = false;

    const raw = fs.readFileSync(this.propsPath, 'utf8');
    this.props = JSON.parse(raw);
    this.serial = this.props['ro.serialno'] || undefined;
    this.deviceFeatures = Array.isArray(this.props.features) ? this.props.features.slice() : [];
  }

  // Given a host CNXN packet (buffer), returns the device CNXN response packet (buffer)
  handleConnect(hostPacketBuffer) {
    // Decode host packet and extract features
    const header = Buffer.isBuffer(hostPacketBuffer) ? hostPacketBuffer.subarray(0, 24) : Buffer.from(hostPacketBuffer).subarray(0, 24);
    if (header.length < 24) throw new Error('Host packet too short');

    const version = header.readUInt32LE(4) >>> 0; // arg0
    const hostMaxData = header.readUInt32LE(8) >>> 0; // arg1
    const payloadLen = header.readUInt32LE(12) >>> 0;
    const payload = hostPacketBuffer.subarray(24, 24 + payloadLen);

    const hostBanner = payload.toString('utf8');
    const hostRequestedFeatures = parseFeaturesFromHostBanner(hostBanner);

    const negotiated = this.deviceFeatures.length
      ? hostRequestedFeatures.filter((f) => this.deviceFeatures.includes(f))
      : hostRequestedFeatures;

    const devVersion = Math.min(this.version, version) >>> 0;
    const devMaxData = Math.min(this.maxData, hostMaxData || ADB_DEFAULT_MAXDATA) >>> 0;

    const banner = buildDeviceBanner({ serial: this.serial, props: this.props, features: negotiated });
    const payloadBuf = Buffer.from(banner, 'utf8');

    const packet = encodePacket({
      command: ADB_CMDS.CNXN,
      arg0: devVersion,
      arg1: devMaxData,
      payload: payloadBuf
    });

    this.connected = true;
    this.negotiatedFeatures = negotiated;
    this.banner = banner;
    this.maxData = devMaxData;

    return packet;
  }
}

export function buildHostConnectPacket({ version = ADB_VERSION, maxData = ADB_DEFAULT_MAXDATA, features = [] } = {}) {
  const banner = `host::features=${features.join(',')}`;
  return encodePacket({
    command: ADB_CMDS.CNXN,
    arg0: version >>> 0,
    arg1: maxDataOrDefault(maxData) >>> 0,
    payload: Buffer.from(banner, 'utf8')
  });
}

export function getDeviceBannerFromProps(propsPath) {
  const raw = fs.readFileSync(propsPath, 'utf8');
  const props = JSON.parse(raw);
  const serial = props['ro.serialno'] || undefined;
  const deviceFeatures = Array.isArray(props.features) ? props.features.slice() : [];
  return buildDeviceBanner({ serial, props, features: deviceFeatures });
}
