"use client";

import { useMemo, useState } from "react";

function imageSrc(src: string | null | undefined) {
  if (!src) {
    return null;
  }

  if (src.startsWith("data:") || /^https?:\/\//i.test(src)) {
    return src;
  }

  const match = src.match(/^\/?listing-images\/([^/]+)$/);
  if (match) {
    return `/api/listing-images/${encodeURIComponent(match[1])}`;
  }

  return src.startsWith("/") ? src : `/${src}`;
}

export function SafeCarImage({
  alt,
  className,
  fallbackClassName,
  src
}: {
  alt: string;
  className: string;
  fallbackClassName: string;
  src: string | null | undefined;
}) {
  const normalizedSrc = useMemo(() => imageSrc(src), [src]);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const shouldShowImage = normalizedSrc && normalizedSrc !== failedSrc;

  if (shouldShowImage) {
    return (
      <img
        alt={alt}
        className={className}
        onError={() => setFailedSrc(normalizedSrc)}
        src={normalizedSrc}
      />
    );
  }

  return (
    <div className={fallbackClassName}>
      <span className="rounded-full bg-white/80 px-3 py-1 text-xs font-bold text-slate-500 shadow-sm">
        No photo
      </span>
    </div>
  );
}
