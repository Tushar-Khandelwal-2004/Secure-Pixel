import { Request, Response } from "express";
import bcrypt from "bcrypt";
import prisma from "../lib/prisma";
import { sendOtpEmail } from "../services/emailService";

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