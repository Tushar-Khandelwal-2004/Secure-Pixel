import { Request, Response } from "express";
import bcrypt from "bcrypt";
import prisma from "../lib/prisma";
import { sendOtpEmail } from "../services/emailService";
import jwt from "jsonwebtoken";
import crypto from "crypto";

const hashToken = (token: string): string => {
    return crypto.createHash("sha256").update(token).digest("hex");
};

export const signup = async (req: Request, res: Response): Promise<any> => {
    try {
        const { first_name, last_name, email, password, x_handle, insta_handle } = req.body;

        // 1. Check if user already exists
        const existingUser = await prisma.user.findUnique({
            where: { email }
        });

        if (existingUser) {
            if (existingUser.is_verified) {
                return res.status(409).json({ error: "Email is already registered" });
            }
            const saltRounds = 10;
            const hashedPassword = await bcrypt.hash(password, saltRounds);
            const otpCode = Math.floor(100000 + Math.random() * 900000).toString();
            const otpExpiry = new Date(Date.now() + 15 * 60 * 1000);
            await prisma.user.update({
                where: { email },
                data: {
                    first_name,
                    last_name,
                    password: hashedPassword, // Crucial: Update the password in case they changed it
                    x_handle,
                    insta_handle,
                    otp_code: otpCode,
                    otp_expiry: otpExpiry,
                },
            });

            await sendOtpEmail(email, otpCode);

            return res.status(200).json({
                message: "Signup restarted. A new OTP has been sent to your email.",
                user_id: existingUser.id,
                email,
            });
        }

        // 2. Hash the password securely (Cost factor of 10)
        const saltRounds = 10;
        const hashedPassword = await bcrypt.hash(password, saltRounds);

        // 3. Generate a secure 6-digit OTP and set expiry (15 mins)
        const otpCode = Math.floor(100000 + Math.random() * 900000).toString();
        const otpExpiry = new Date(Date.now() + 15 * 60 * 1000);

        // 4. Create the unverified user in the database
        const newUser = await prisma.user.create({
            data: {
                first_name,
                last_name,
                email,
                password: hashedPassword,
                x_handle,
                insta_handle,
                is_verified: false,
                otp_code: otpCode,
                otp_expiry: otpExpiry,
            }
        });

        await sendOtpEmail(email, otpCode);
        console.log(`[EMAIL MOCK] Sending OTP ${otpCode} to ${email}`);

        // 6. Respond to the frontend
        res.status(201).json({
            message: "User registered successfully. Please check your email for the OTP.",
            user_id: newUser.id,
            email: newUser.email
        });

    } catch (error) {
        console.error("Signup error:", error);
        res.status(500).json({ error: "Internal server error during signup" });
    }
};

export const verifyOtp = async (req: Request, res: Response): Promise<any> => {
    try {
        const { email, otp_code } = req.body;

        const user = await prisma.user.findUnique({ where: { email } });

        if (!user) {
            return res.status(404).json({ error: "User not found" });
        }

        if (user.is_verified) {
            return res.status(400).json({ error: "User is already verified" });
        }

        if (user.otp_code !== otp_code) {
            return res.status(400).json({ error: "Invalid OTP code" });
        }

        if (!user.otp_expiry || user.otp_expiry < new Date()) {
            return res.status(400).json({ error: "OTP has expired. Please request a new one." });
        }

        await prisma.user.update({
            where: { email },
            data: {
                is_verified: true,
                otp_code: null,
                otp_expiry: null
            }
        });

        res.status(200).json({ message: "Account successfully verified. You can now log in." });
    } catch (error) {
        console.error("OTP verification error:", error);
        res.status(500).json({ error: "Internal server error during verification" });
    }
};

export const resendOtp = async (req: Request, res: Response): Promise<any> => {
    try {
        const { email } = req.body;

        const user = await prisma.user.findUnique({ where: { email } });

        if (!user) {
            return res.status(404).json({ error: "User not found" });
        }

        if (user.is_verified) {
            return res.status(400).json({ error: "User is already verified. Please sign in." });
        }

        // Generate fresh OTP
        const otpCode = Math.floor(100000 + Math.random() * 900000).toString();
        const otpExpiry = new Date(Date.now() + 15 * 60 * 1000);

        await prisma.user.update({
            where: { email },
            data: {
                otp_code: otpCode,
                otp_expiry: otpExpiry,
            },
        });

        await sendOtpEmail(email, otpCode);

        res.status(200).json({ message: "A new OTP has been sent to your email." });
    } catch (error) {
        console.error("Resend OTP error:", error);
        res.status(500).json({ error: "Internal server error while resending OTP" });
    }
};

export const signin = async (req: Request, res: Response): Promise<any> => {
    try {
        const { email, password } = req.body;

        const user = await prisma.user.findUnique({ where: { email } });

        if (!user) {
            return res.status(401).json({ error: "Invalid email or password" });
        }

        if (!user.is_verified) {
            return res.status(403).json({ error: "Please verify your email before signing in." });
        }

        const isPasswordValid = await bcrypt.compare(password, user.password);

        if (!isPasswordValid) {
            return res.status(401).json({ error: "Invalid email or password" });
        }

        const accessToken = jwt.sign(
            { userId: user.id, email: user.email },
            process.env.JWT_SECRET as string,
            { expiresIn: "15m" }
        );

        const refreshToken = jwt.sign(
            { userId: user.id },
            process.env.JWT_REFRESH_SECRET as string,
            { expiresIn: "7d" }
        );

        const hashedRefreshToken = hashToken(refreshToken);

        await prisma.refreshToken.create({
            data: {
                token: hashedRefreshToken,
                userId: user.id,
            },
        });

        res.cookie("refreshToken", refreshToken, {
            httpOnly: true, // Prevents XSS attacks (JS cannot read this)
            secure: process.env.NODE_ENV === "production", // Only sends over HTTPS in production
            sameSite: "strict", // Prevents CSRF attacks
            maxAge: 7 * 24 * 60 * 60 * 1000, // 7 days in milliseconds
        });

        res.status(200).json({
            message: "Signed in successfully",
            accessToken,
            user: {
                id: user.id,
                first_name: user.first_name,
                last_name: user.last_name,
                email: user.email,
                profile_photo: user.profile_photo
            }
        });

    } catch (error) {
        console.error("Signin error:", error);
        res.status(500).json({ error: "Internal server error during signin" });
    }
};

export const refresh = async (req: Request, res: Response): Promise<any> => {
    try {
        const refreshToken = req.cookies.refreshToken;

        if (!refreshToken) {
            return res.status(401).json({ error: "No refresh token provided." });
        }

        res.clearCookie("refreshToken", {
            httpOnly: true,
            secure: process.env.NODE_ENV === "production",
            sameSite: "strict"
        });

        const hashedIncomingToken = hashToken(refreshToken);

        const foundToken = await prisma.refreshToken.findUnique({
            where: { token: hashedIncomingToken }
        });

        if (!foundToken) {
            try {
                const decoded = jwt.verify(
                    refreshToken,
                    process.env.JWT_REFRESH_SECRET as string
                ) as { userId: string };

                await prisma.refreshToken.deleteMany({
                    where: { userId: decoded.userId }
                });

                return res.status(403).json({
                    error: "Security breach detected. Please log in again."
                });

            } catch (err) {
                return res.status(403).json({ error: "Invalid refresh token." });
            }
        }

        await prisma.refreshToken.delete({
            where: { id: foundToken.id }
        });

        const decoded = jwt.verify(
            refreshToken,
            process.env.JWT_REFRESH_SECRET as string
        ) as { userId: string };

        const user = await prisma.user.findUnique({
            where: { id: decoded.userId }
        });

        if (!user) {
            return res.status(401).json({ error: "User no longer exists." });
        }

        const newAccessToken = jwt.sign(
            { userId: user.id, email: user.email },
            process.env.JWT_SECRET as string,
            { expiresIn: "15m" }
        );

        const newRefreshToken = jwt.sign(
            { userId: user.id },
            process.env.JWT_REFRESH_SECRET as string,
            { expiresIn: "7d" }
        );

        const hashedNewToken = hashToken(newRefreshToken);

        await prisma.refreshToken.create({
            data: {
                token: hashedNewToken,
                userId: user.id
            }
        });

        res.cookie("refreshToken", newRefreshToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === "production",
            sameSite: "strict",
            maxAge: 7 * 24 * 60 * 60 * 1000,
        });

        res.status(200).json({ accessToken: newAccessToken });

    } catch (error) {
        console.error("Refresh token error:", error);
        res.status(403).json({
            error: "Invalid or expired refresh token. Please log in again."
        });
    }
};

export const signout = async (req: Request, res: Response): Promise<any> => {
    try {
        const refreshToken = req.cookies.refreshToken;
        const { allDevices } = req.body; // e.g., { "allDevices": true }

        if (refreshToken) {
            if (allDevices) {
                const decoded = jwt.verify(refreshToken, process.env.JWT_REFRESH_SECRET as string) as { userId: string };
                await prisma.refreshToken.deleteMany({
                    where: { userId: decoded.userId }
                });
            } else {
                const hashedToken = hashToken(refreshToken);
                await prisma.refreshToken.deleteMany({
                    where: { token: hashedToken }
                });
            }
        }

        res.clearCookie("refreshToken", {
            httpOnly: true,
            secure: process.env.NODE_ENV === "production",
            sameSite: "strict",
        });

        res.status(200).json({ message: allDevices ? "Signed out of all devices" : "Successfully signed out" });
    } catch (error) {
        console.error("Signout error:", error);
        res.clearCookie("refreshToken");
        res.status(200).json({ message: "Signed out completely" });
    }
};