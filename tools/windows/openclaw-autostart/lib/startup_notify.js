'use strict';

function shouldSendForBoot(state, bootId, force = false) {
  if (force) return true;
  return state?.lastBootId !== bootId;
}

function buildStartupMessage({
  hostname,
  bootId,
  nowIso,
  gatewayPort = 18789,
  source = 'watchdog',
}) {
  return [
    'OpenClaw 开机自启动成功',
    `时间: ${nowIso}`,
    `主机: ${hostname}`,
    `Gateway: 127.0.0.1:${gatewayPort} OK`,
    `来源: ${source}`,
    `BootId: ${bootId}`,
  ].join('\n');
}

function nextState(bootId, nowIso, messageId) {
  return {
    lastBootId: bootId,
    lastSentAt: nowIso,
    lastMessageId: messageId || '',
  };
}

module.exports = {
  shouldSendForBoot,
  buildStartupMessage,
  nextState,
};

