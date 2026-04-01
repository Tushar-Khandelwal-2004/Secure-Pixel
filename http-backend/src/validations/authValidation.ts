import { z } from "zod";

export const signupSchema = z.object({
  body: z.object({
    first_name: z.string()
      .min(2, "First name must be at least 2 characters")
      .regex(/^[A-Za-z]+$/, "First name must contain only letters"),
    
    last_name: z.string()
      .min(1, "Last name is required")
      .regex(/^[A-Za-z]+$/, "Last name must contain only letters"),
    
    email: z.email("Please provide a valid email address"),
    
    password: z.string()
      .min(8, "Password must be at least 8 characters")
      .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
      .regex(/[0-9]/, "Password must contain at least one number"),
      
    x_handle: z.string()
      .regex(/^@[A-Za-z0-9_]{1,15}$/, "Invalid X handle format. Must start with @")
      .optional()
      .or(z.literal("")), // Allows empty string if they skip it
      
    insta_handle: z.string()
      .regex(/^[A-Za-z0-9_.]+$/, "Invalid Instagram handle format")
      .optional()
      .or(z.literal(""))
  })
});
export const verifyOtpSchema = z.object({
  body: z.object({
    email: z.string().email("Invalid email address"),
    otp_code: z.string().length(6, "OTP must be exactly 6 digits")
  })
});

export const resendOtpSchema = z.object({
  body: z.object({
    email: z.string().email("Invalid email address")
  })
});