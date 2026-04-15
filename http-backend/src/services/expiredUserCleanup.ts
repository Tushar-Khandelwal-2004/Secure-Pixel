import prisma from "../lib/prisma";

const CLEANUP_INTERVAL_MS = 60 * 60 * 1000;
const EXPIRED_USER_GRACE_PERIOD_MS = 24 * 60 * 60 * 1000;

let cleanupTimer: NodeJS.Timeout | null = null;
let isCleanupRunning = false;

export const deleteExpiredUnverifiedUsers = async (): Promise<number> => {
  const cutoff = new Date(Date.now() - EXPIRED_USER_GRACE_PERIOD_MS);

  const result = await prisma.user.deleteMany({
    where: {
      is_verified: false,
      otp_expiry: {
        lt: cutoff,
      },
    },
  });

  return result.count;
};

const runExpiredUserCleanup = async () => {
  if (isCleanupRunning) return;

  isCleanupRunning = true;
  try {
    const deletedCount = await deleteExpiredUnverifiedUsers();
    if (deletedCount > 0) {
      console.log(`Deleted ${deletedCount} expired unverified user(s).`);
    }
  } catch (error) {
    console.error("Expired unverified user cleanup failed:", error);
  } finally {
    isCleanupRunning = false;
  }
};

export const startExpiredUserCleanup = () => {
  if (cleanupTimer) return;

  void runExpiredUserCleanup();
  cleanupTimer = setInterval(() => {
    void runExpiredUserCleanup();
  }, CLEANUP_INTERVAL_MS);
  cleanupTimer.unref();
};
