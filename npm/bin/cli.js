#!/usr/bin/env node
'use strict';

/**
 * UNITY SENTINEL — npx entry point.
 *
 * Usage:
 *   npx unity-sentinel init
 *   npx unity-sentinel init --agents claude,codex,cursor,generic --team
 *   npx unity-sentinel scan --project .
 *   npx unity-sentinel team
 */

const { main } = require('../lib/cli');

main(process.argv.slice(2)).then(
  (code) => {
    process.exitCode = code;
  },
  (error) => {
    // eslint-disable-next-line no-console
    console.error(`unity-sentinel: ${error && error.message ? error.message : error}`);
    process.exitCode = 3;
  },
);
