import nodemailer from "nodemailer";

if (!process.env.SMTP_USER || !process.env.SMTP_PASS) {
  throw new Error("SMTP credentials missing");
}

const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST || "smtp.gmail.com",
  port: Number(process.env.SMTP_PORT) || 465,
  secure: true, 
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASS,
  },
});

export const sendOtpEmail = async (to: string, otpCode: string) => {
  try {
    await transporter.sendMail({
      from: `"SecurePixel Security" <${process.env.SMTP_USER}>`,
      to,
      subject: "Verify Your SecurePixel Account",
      text: `Your verification code is: ${otpCode}. It expires in 15 minutes.`,
      html: `
        <p>Your verification code is: <strong>${otpCode}</strong></p>
        <p>It expires in 15 minutes.</p>
      `,
    });

    console.log(`OTP sent successfully to ${to}`);
  } catch (error) {
    console.error("Failed to send OTP email:", error);
    throw new Error("Email delivery failed");
  }
};