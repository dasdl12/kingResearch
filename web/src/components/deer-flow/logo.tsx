// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import Image from "next/image";
import Link from "next/link";

export function Logo() {
  return (
    <Link
      className="flex items-center gap-2 opacity-70 transition-opacity duration-300 hover:opacity-100"
      href="/"
    >
      <Image
        src="/images/logo.png"
        alt="KingSearch Logo"
        width={150}
        height={62}
        className="object-contain"
      />
    </Link>
  );
}
