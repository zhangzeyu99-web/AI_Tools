'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  shouldSendForBoot,
  buildStartupMessage,
  nextState,
} = require('./lib/startup_notify.js');

const STATE_PATH = path.join(process.env.USERPROFILE || os.homedir(), '.openclaw', 'state', 'startup-notify-state.json');
const CONFIG_PATH = path.join(process.env.USERPROFILE || os.homedir(), '.openclaw', 'openclaw.json');

function parseArgs(argv) {
  const result = {
    bootId: '',
    source: 'watchdog',
    gatewayPort: 18789,
    force: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--boot-id') result.bootId = argv[i + 1] || '';
    if (arg === '--source') result.source = argv[i + 1] || result.source;
    if (arg === '--gateway-port') result.gatewayPort = Number(argv[i + 1] || result.gatewayPort);
    if (arg === '--force') result.force = true;
  }
  return result;
}

function readJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

function getFeishuTarget() {
  const config = readJson(CONFIG_PATH, {});
  const feishu = config?.channels?.feishu || {};
  const accounts = feishu.accounts || {};
  const bot = accounts['bot-xiaoxia'] || {};
  const appId = bot.appId || feishu.appId || '';
  const appSecret = bot.appSecret || feishu.appSecret || '';
  const allowFrom = bot.groupAllowFrom || feishu.groupAllowFrom || [];
  const openId = allowFrom[0] || '';
  if (!appId || !appSecret || !openId) {
    throw new Error('Feishu bot-xiaoxia credentials or target open_id missing');
  }
  return { appId, appSecret, openId };
}

async function getTenantToken(appId, appSecret) {
  const response = await fetch('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ app_id: appId, app_secret: appSecret }),
  });
  const data = await response.json();
  if (!response.ok || !data.tenant_access_token) {
    throw new Error(`Feishu token error: code=${data.code} msg=${data.msg}`);
  }
  return data.tenant_access_token;
}

async function sendTextMessage(token, openId, text) {
  const response = await fetch('https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json; charset=utf-8',
    },
    body: JSON.stringify({
      receive_id: openId,
      msg_type: 'text',
      content: JSON.stringify({ text }),
    }),
  });
  const data = await response.json();
  if (!response.ok || data.code !== 0) {
    throw new Error(`Feishu send error: code=${data.code} msg=${data.msg}`);
  }
  return data.data?.message_id || '';
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.bootId) {
    throw new Error('Missing --boot-id');
  }

  const state = readJson(STATE_PATH, {});
  if (!shouldSendForBoot(state, args.bootId, args.force)) {
    process.stdout.write(`${JSON.stringify({ sent: false, reason: 'already-notified', bootId: args.bootId })}\n`);
    return;
  }

  const target = getFeishuTarget();
  const nowIso = new Date().toISOString();
  const text = buildStartupMessage({
    hostname: os.hostname(),
    bootId: args.bootId,
    nowIso,
    gatewayPort: args.gatewayPort,
    source: args.source,
  });
  const token = await getTenantToken(target.appId, target.appSecret);
  const messageId = await sendTextMessage(token, target.openId, text);
  writeJson(STATE_PATH, nextState(args.bootId, nowIso, messageId));
  process.stdout.write(`${JSON.stringify({ sent: true, bootId: args.bootId, messageId })}\n`);
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exitCode = 1;
});

