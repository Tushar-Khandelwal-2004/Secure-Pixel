import { PrismaClient } from "@prisma/client";

declare global {
  var __prisma: PrismaClient | undefined;
}

const prisma =
  process.env.NODE_ENV === "production"
    ? new PrismaClient()
    : (globalThis.__prisma ??= new PrismaClient());

export default prisma;
