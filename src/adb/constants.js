// ADB command constants and helpers

export const ADB_CMDS = {
  SYNC: 0x434e5953, // 'SYNC'
  CNXN: 0x4e584e43, // 'CNXN'
  OPEN: 0x4e45504f, // 'OPEN'
  OKAY: 0x59414b4f, // 'OKAY'
  CLSE: 0x45534c43, // 'CLSE'
  WRTE: 0x45545257  // 'WRTE'
};

export const ADB_VERSION = 0x01000000; // protocol version 1.0
export const ADB_DEFAULT_MAXDATA = 4096;

const STR_TO_CMD = {
  SYNC: ADB_CMDS.SYNC,
  CNXN: ADB_CMDS.CNXN,
  OPEN: ADB_CMDS.OPEN,
  OKAY: ADB_CMDS.OKAY,
  CLSE: ADB_CMDS.CLSE,
  WRTE: ADB_CMDS.WRTE
};

const CMD_TO_STR = Object.fromEntries(Object.entries(STR_TO_CMD).map(([k, v]) => [v, k]));

export function commandFromString(cmdStr) {
  if (!STR_TO_CMD[cmdStr]) throw new Error(`Unknown ADB command string: ${cmdStr}`);
  return STR_TO_CMD[cmdStr];
}

export function commandToString(cmd) {
  return CMD_TO_STR[cmd] || `0x${cmd.toString(16)}`;
}
