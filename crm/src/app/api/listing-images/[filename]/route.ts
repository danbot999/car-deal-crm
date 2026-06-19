import { readFile, stat } from "node:fs/promises";
import { extname, resolve } from "node:path";

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    filename: string;
  }>;
};

const contentTypes: Record<string, string> = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp"
};

function publicImageRoot() {
  return resolve(process.cwd(), "public", "listing-images");
}

export async function GET(_request: Request, context: RouteContext) {
  const { filename } = await context.params;

  if (!/^[a-zA-Z0-9_.-]+\.(?:jpe?g|png|webp)$/.test(filename)) {
    return NextResponse.json({ error: "Invalid image path." }, { status: 400 });
  }

  const root = publicImageRoot();
  const imagePath = resolve(root, filename);

  if (!imagePath.startsWith(root)) {
    return NextResponse.json({ error: "Invalid image path." }, { status: 400 });
  }

  try {
    const imageStat = await stat(imagePath);
    if (!imageStat.isFile()) {
      return NextResponse.json({ error: "Image not found." }, { status: 404 });
    }

    const extension = extname(imagePath).toLowerCase();
    const bytes = await readFile(imagePath);

    return new NextResponse(bytes, {
      headers: {
        "Cache-Control": "public, max-age=3600",
        "Content-Type": contentTypes[extension] ?? "application/octet-stream"
      }
    });
  } catch {
    return NextResponse.json({ error: "Image not found." }, { status: 404 });
  }
}
