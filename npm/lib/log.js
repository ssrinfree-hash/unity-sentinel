'use strict';

const supportsColor = process.stdout.isTTY && !process.env.NO_COLOR;

function wrap(code, text) {
  return supportsColor ? `\u001b[${code}m${text}\u001b[0m` : String(text);
}

module.exports = {
  bold: (text) => wrap('1', text),
  dim: (text) => wrap('2', text),
  green: (text) => wrap('32', text),
  yellow: (text) => wrap('33', text),
  red: (text) => wrap('31', text),
  cyan: (text) => wrap('36', text),
  info: (text) => console.log(`${wrap('36', 'info')}  ${text}`),
  ok: (text) => console.log(`${wrap('32', 'ok')}    ${text}`),
  warn: (text) => console.log(`${wrap('33', 'warn')}  ${text}`),
  error: (text) => console.error(`${wrap('31', 'error')} ${text}`),
  plain: (text) => console.log(text),
};
