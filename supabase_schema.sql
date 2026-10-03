-- =============================================================================
-- Road Damage Reporting Platform - Production Supabase PostgreSQL Schema
-- Architecture v2.0 - Fully Integrated Hackathon Specification
-- =============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -----------------------------------------------------------------------------
-- 1. Jurisdictions Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.jurisdictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    contact_email VARCHAR(255),
    boundary_geojson JSONB,
    active_crew_count INT NOT NULL DEFAULT 3,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed Initial Jurisdictions
INSERT INTO public.jurisdictions (name, code, contact_email, active_crew_count)
VALUES 
    ('Metro Central District', 'METRO-C', 'central.dispatch@cityworks.gov', 5),
    ('North Highway Division', 'HIGHWAY-N', 'north.maintenance@cityworks.gov', 4),
    ('South Suburban Precinct', 'SUBURB-S', 'south.roads@cityworks.gov', 3),
    ('East Industrial Sector', 'IND-E', 'east.works@cityworks.gov', 2),
    ('West Coastal Zone', 'COAST-W', 'west.infrastructure@cityworks.gov', 3)
ON CONFLICT (code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 2. Reports Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_url TEXT NOT NULL,
    latitude FLOAT8 NOT NULL,
    longitude FLOAT8 NOT NULL,
    damage_type VARCHAR(50) NOT NULL, -- e.g. 'pothole', 'crack', 'surface wear', 'edge break'
    severity VARCHAR(20) NOT NULL,    -- 'Low', 'Medium', 'High', 'Critical'
    confidence FLOAT4 NOT NULL,       -- Model confidence score between 0.0 and 1.0
    priority_score INT NOT NULL,      -- Composite priority score between 0 and 100
    status VARCHAR(30) NOT NULL DEFAULT 'Reported', -- 'Reported', 'Assigned', 'In Progress', 'Resolved'
    road_class VARCHAR(50) NOT NULL DEFAULT 'Local Street', -- 'Highway / Arterial', 'Collector / Main Ave', 'Local Street', 'Residential'
    bbox JSONB DEFAULT '[]'::jsonb,   -- Array of bounding box detections: [{"x1", "y1", "x2", "y2", "label", "confidence"}]
    assigned_crew VARCHAR(100),
    jurisdiction_id UUID REFERENCES public.jurisdictions(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_report_severity CHECK (severity IN ('Low', 'Medium', 'High', 'Critical')),
    CONSTRAINT chk_report_status CHECK (status IN ('Reported', 'Assigned', 'In Progress', 'Resolved')),
    CONSTRAINT chk_priority_score CHECK (priority_score >= 0 AND priority_score <= 100),
    CONSTRAINT chk_confidence_range CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

-- -----------------------------------------------------------------------------
-- 3. Status Updates (Audit Log & Triage History)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.status_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES public.reports(id) ON DELETE CASCADE,
    previous_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,
    changed_by VARCHAR(100) NOT NULL DEFAULT 'Municipal Operator',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 4. High-Performance Indexes
-- -----------------------------------------------------------------------------
-- Priority score index for fast priority queue sorting
CREATE INDEX IF NOT EXISTS idx_reports_priority_score ON public.reports (priority_score DESC);

-- Spatial coordinates index for map bounds and geographic queries
CREATE INDEX IF NOT EXISTS idx_reports_coordinates ON public.reports (latitude, longitude);

-- Status index for fast filtering in triage queues
CREATE INDEX IF NOT EXISTS idx_reports_status ON public.reports (status);

-- Damage type and severity indexes
CREATE INDEX IF NOT EXISTS idx_reports_damage_type ON public.reports (damage_type);
CREATE INDEX IF NOT EXISTS idx_reports_severity ON public.reports (severity);

-- Chronological indexes
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON public.reports (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_status_updates_report_id ON public.status_updates (report_id);

-- -----------------------------------------------------------------------------
-- 5. Automated Updated-At & Status Audit Triggers
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_handle_report_update()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();

    -- Automatically append an entry to status_updates whenever status changes
    IF (OLD.status IS DISTINCT FROM NEW.status) THEN
        INSERT INTO public.status_updates (report_id, previous_status, new_status, changed_by, notes)
        VALUES (
            NEW.id,
            OLD.status,
            NEW.status,
            COALESCE(NEW.assigned_crew, 'Triage Officer'),
            NEW.notes
        );
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reports_update ON public.reports;
CREATE TRIGGER trg_reports_update
    BEFORE UPDATE ON public.reports
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_handle_report_update();

-- -----------------------------------------------------------------------------
-- 6. Row Level Security (RLS) Policies
-- -----------------------------------------------------------------------------
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jurisdictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.status_updates ENABLE ROW LEVEL SECURITY;

-- Reports: Allow anonymous public citizens to INSERT reports
CREATE POLICY "Public anonymous citizens can submit damage reports"
    ON public.reports FOR INSERT
    TO anon, authenticated
    WITH CHECK (true);

-- Reports: Allow public reading of reports (for transparency and dashboard)
CREATE POLICY "Allow public read access to damage reports"
    ON public.reports FOR SELECT
    TO anon, authenticated
    USING (true);

-- Reports: Allow authenticated/service role to update reports (triage actions)
CREATE POLICY "Allow authorities to update damage reports"
    ON public.reports FOR UPDATE
    TO anon, authenticated
    USING (true)
    WITH CHECK (true);

-- Jurisdictions: Allow read access to all
CREATE POLICY "Allow read access to jurisdictions"
    ON public.jurisdictions FOR SELECT
    TO anon, authenticated
    USING (true);

-- Status Updates: Allow reading and writing
CREATE POLICY "Allow read status updates"
    ON public.status_updates FOR SELECT
    TO anon, authenticated
    USING (true);

CREATE POLICY "Allow insert status updates"
    ON public.status_updates FOR INSERT
    TO anon, authenticated
    WITH CHECK (true);

-- -----------------------------------------------------------------------------
-- 7. Supabase Storage Bucket Setup for Road Damage Media
-- -----------------------------------------------------------------------------
-- Create storage bucket for road damage media
INSERT INTO storage.buckets (id, name, public)
VALUES ('road-damage-media', 'road-damage-media', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- Allow public uploads to storage bucket
CREATE POLICY "Public can upload damage images"
    ON storage.objects FOR INSERT
    TO anon, authenticated
    WITH CHECK (bucket_id = 'road-damage-media');

-- Allow public reads from storage bucket
CREATE POLICY "Public can view damage images"
    ON storage.objects FOR SELECT
    TO anon, authenticated
    USING (bucket_id = 'road-damage-media');

-- -----------------------------------------------------------------------------
-- 8. Realtime Replication Publication
-- -----------------------------------------------------------------------------
-- Ensure reports table is included in Supabase realtime publications
ALTER PUBLICATION supabase_realtime ADD TABLE public.reports;
ALTER PUBLICATION supabase_realtime ADD TABLE public.status_updates;

-- -----------------------------------------------------------------------------
-- 9. Analytical Views
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.vw_triage_analytics AS
SELECT 
    COUNT(*) AS total_reports,
    COUNT(*) FILTER (WHERE status = 'Reported') AS pending_triage,
    COUNT(*) FILTER (WHERE status = 'Assigned') AS assigned,
    COUNT(*) FILTER (WHERE status = 'In Progress') AS in_progress,
    COUNT(*) FILTER (WHERE status = 'Resolved') AS resolved,
    COUNT(*) FILTER (WHERE severity = 'Critical') AS critical_hazards,
    COUNT(*) FILTER (WHERE priority_score >= 75) AS high_priority_count,
    ROUND(AVG(priority_score)::numeric, 1) AS avg_priority_score
FROM public.reports;
