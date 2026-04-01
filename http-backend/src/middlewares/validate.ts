import { Request, Response, NextFunction } from "express";
import { ZodObject, ZodError, ZodIssue } from "zod";

export const validate = (schema: ZodObject<any>) =>
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      await schema.parseAsync({
        body: req.body,
        query: req.query,
        params: req.params,
      });

      return next();
    } catch (error) {
      if (error instanceof ZodError) {
        const errorMessages = error.issues.map((err: ZodIssue) => ({
          field: err.path.join("."),
          message: err.message,
        }));

        return res.status(400).json({ errors: errorMessages });
      }

      return res.status(400).json({ error: "Internal validation error" });
    }
  };