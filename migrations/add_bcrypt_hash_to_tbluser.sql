-- Migration: add BcryptHash column to tblUser
-- Run once per site database (escaperoadx_pg, snowrider_pg, etc.)
-- Safe to run multiple times (IF NOT EXISTS).

ALTER TABLE "tblUser"
    ADD COLUMN IF NOT EXISTS "BcryptHash" VARCHAR(255) NULL;
