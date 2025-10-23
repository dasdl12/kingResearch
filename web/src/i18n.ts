// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { getRequestConfig } from "next-intl/server";

// Force Chinese language only
export default getRequestConfig(async () => {
  return {
    messages: (await import(`../messages/zh.json`)).default,
    locale: "zh",
  };
});
