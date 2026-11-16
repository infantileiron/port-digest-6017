--
-- 002：对外公开申请、冻结来源与公开记录
-- 与 ORM 首次建表等价；系统无在线迁移执行器，本文件保留实际 DDL。
--

CREATE TABLE public.disclosure_sources (
    id integer NOT NULL,
    report_day character varying(10) NOT NULL,
    snapshot json NOT NULL,
    fingerprint character varying(64) NOT NULL,
    created_at character varying(40),
    created_by character varying(100)
);

CREATE SEQUENCE public.disclosure_sources_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

ALTER SEQUENCE public.disclosure_sources_id_seq OWNED BY public.disclosure_sources.id;

ALTER TABLE ONLY public.disclosure_sources ALTER COLUMN id SET DEFAULT nextval('public.disclosure_sources_id_seq'::regclass);

ALTER TABLE ONLY public.disclosure_sources
    ADD CONSTRAINT disclosure_sources_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.disclosure_sources
    ADD CONSTRAINT uq_disclosure_source_day UNIQUE (report_day);

CREATE TABLE public.disclosure_applications (
    id integer NOT NULL,
    report_day character varying(10) NOT NULL,
    station character varying(80) NOT NULL,
    stations json NOT NULL,
    requested_by character varying(100),
    request_note text,
    created_at character varying(40),
    state character varying(20),
    decided_at character varying(40),
    decided_by character varying(100),
    decision_note text,
    basis json,
    disclosure_id integer
);

CREATE SEQUENCE public.disclosure_applications_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

ALTER SEQUENCE public.disclosure_applications_id_seq OWNED BY public.disclosure_applications.id;

ALTER TABLE ONLY public.disclosure_applications ALTER COLUMN id SET DEFAULT nextval('public.disclosure_applications_id_seq'::regclass);

ALTER TABLE ONLY public.disclosure_applications
    ADD CONSTRAINT disclosure_applications_pkey PRIMARY KEY (id);

CREATE TABLE public.disclosures (
    id integer NOT NULL,
    application_id integer,
    report_day character varying(10) NOT NULL,
    station character varying(80) NOT NULL,
    stations json NOT NULL,
    source_id integer NOT NULL,
    published_at character varying(40),
    published_by character varying(100),
    payload json,
    checksum character varying(64),
    version character varying(60),
    rule text
);

CREATE SEQUENCE public.disclosures_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

ALTER SEQUENCE public.disclosures_id_seq OWNED BY public.disclosures.id;

ALTER TABLE ONLY public.disclosures ALTER COLUMN id SET DEFAULT nextval('public.disclosures_id_seq'::regclass);

ALTER TABLE ONLY public.disclosures
    ADD CONSTRAINT disclosures_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.disclosures
    ADD CONSTRAINT uq_disclosure_day_station UNIQUE (report_day, station);

ALTER TABLE ONLY public.disclosures
    ADD CONSTRAINT disclosures_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.disclosure_applications(id);

ALTER TABLE ONLY public.disclosures
    ADD CONSTRAINT disclosures_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.disclosure_sources(id);
