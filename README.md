# Aurelia Engine 🔒

Motor de processamento de áudio do AudioBuilder. API REST dockerizada que roda o sistema de cloaking Aurelia.

## Arquitetura

```
┌─────────────────┐       HTTPS + API Key       ┌──────────────────┐
│   AudioBuilder   │ ──────────────────────────► │  Aurelia Engine  │
│   (Next.js)      │                             │  (FastAPI/Docker)│
│   Vercel/etc     │ ◄────────────────────────── │  VPS Hostinger   │
└─────────────────┘     JSON + File download     └──────────────────┘
```

**Fluxo:**
1. AudioBuilder faz upload do vídeo para Aurelia via `POST /api/v1/process`
2. Aurelia processa em background (dual-stream cloaking)
3. AudioBuilder faz polling em `GET /api/v1/status/{job_id}`
4. Quando `completed`, AudioBuilder baixa via `GET /api/v1/download/{job_id}`

---

## Deploy na VPS Hostinger

### Pré-requisitos
- VPS Ubuntu 22.04 ou 24.04
- Mínimo 2GB RAM, 2 vCPU (recomendado 4GB)
- Domínio apontando para o IP da VPS (ex: `aurelia.audiobuilder.com.br`)

### Passo a passo

```bash
# 1. Upload do projeto para a VPS
scp aurelia-engine.zip root@SEU_IP:~/
ssh root@SEU_IP

# 2. Descompactar
unzip aurelia-engine.zip -d aurelia-engine
cd aurelia-engine

# 3. Rodar setup automático
chmod +x setup-vps.sh
./setup-vps.sh

# 4. Configurar Nginx + SSL (após DNS propagado)
sudo cp nginx/aurelia.conf /etc/nginx/sites-available/aurelia
sudo ln -s /etc/nginx/sites-available/aurelia /etc/nginx/sites-enabled/
# Edite o server_name se seu domínio for diferente:
sudo nano /etc/nginx/sites-available/aurelia
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d aurelia.audiobuilder.com.br
```

### Testar

```bash
# Health check
curl https://aurelia.audiobuilder.com.br/health

# Processar um vídeo
curl -X POST https://aurelia.audiobuilder.com.br/api/v1/process \
  -H "X-Api-Key: SUA_API_KEY" \
  -F "file=@video.mp4" \
  -F "category=general" \
  -F "strategy=dual"

# Checar status
curl https://aurelia.audiobuilder.com.br/api/v1/status/JOB_ID \
  -H "X-Api-Key: SUA_API_KEY"

# Baixar resultado
curl -O https://aurelia.audiobuilder.com.br/api/v1/download/JOB_ID \
  -H "X-Api-Key: SUA_API_KEY"
```

---

## API Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/health` | Health check (sem auth) |
| `POST` | `/api/v1/process` | Upload + iniciar processamento |
| `GET` | `/api/v1/status/{job_id}` | Status do job |
| `GET` | `/api/v1/download/{job_id}` | Download do resultado |

### POST /api/v1/process

**Headers:** `X-Api-Key: sua-chave`

**Form data:**
- `file` — Arquivo de vídeo (mp4, mov, mkv, avi, webm, mp3, wav, m4a)
- `category` — Categoria do white loss: `weight_loss`, `ed`, `supplements`, `skincare`, `fitness`, `general`, `random`
- `strategy` — Estratégia: `dual` (recomendado), `hybrid`, `spectral`

**Response:**
```json
{
  "job_id": "uuid-aqui",
  "status": "queued",
  "message": "Processing started. Poll /api/v1/status/{job_id} for updates."
}
```

### GET /api/v1/status/{job_id}

**Response:**
```json
{
  "job_id": "uuid",
  "status": "completed",
  "filename": "video_shielded.mp4",
  "download_url": "/api/v1/download/uuid",
  "created_at": "2026-03-05T10:00:00"
}
```

Status possíveis: `queued` → `processing` → `completed` | `failed`

---

## Integração com AudioBuilder (Next.js)

### 1. Adicione ao `.env` do AudioBuilder:

```env
AURELIA_ENGINE_URL=https://aurelia.audiobuilder.com.br
AURELIA_API_KEY=sua-chave-gerada-no-setup
```

### 2. Adicione ao `env.server.ts`:

```ts
const schema = z.object({
  SUPABASE_SERVICE_ROLE_KEY: z.string().min(20),
  DATABASE_URL: z.string().min(10),
  AURELIA_ENGINE_URL: z.string().url(),
  AURELIA_API_KEY: z.string().min(10),
});
```

### 3. Crie `src/server/aurelia/client.ts`:

```ts
import "server-only";
import { envServer } from "@/shared/config/env.server";

const BASE_URL = envServer.AURELIA_ENGINE_URL;
const API_KEY = envServer.AURELIA_API_KEY;

export async function submitToAurelia(params: {
  fileBuffer: Buffer;
  filename: string;
  category?: string;
  strategy?: string;
}) {
  const formData = new FormData();
  const blob = new Blob([params.fileBuffer]);
  formData.append("file", blob, params.filename);
  formData.append("category", params.category || "general");
  formData.append("strategy", params.strategy || "dual");

  const res = await fetch(`${BASE_URL}/api/v1/process`, {
    method: "POST",
    headers: { "X-Api-Key": API_KEY },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Aurelia error: ${res.status}`);
  }

  return res.json() as Promise<{ job_id: string; status: string }>;
}

export async function getAureliaStatus(jobId: string) {
  const res = await fetch(`${BASE_URL}/api/v1/status/${jobId}`, {
    headers: { "X-Api-Key": API_KEY },
    cache: "no-store",
  });

  if (!res.ok) throw new Error(`Status check failed: ${res.status}`);

  return res.json() as Promise<{
    job_id: string;
    status: string;
    filename?: string;
    download_url?: string;
    error?: string;
  }>;
}

export async function downloadFromAurelia(jobId: string): Promise<Buffer> {
  const res = await fetch(`${BASE_URL}/api/v1/download/${jobId}`, {
    headers: { "X-Api-Key": API_KEY },
  });

  if (!res.ok) throw new Error(`Download failed: ${res.status}`);

  const arrayBuffer = await res.arrayBuffer();
  return Buffer.from(arrayBuffer);
}
```

### 4. Atualize `/api/process-video/route.ts`:

Substitua o processamento local (FFmpeg direto) por chamadas ao Aurelia Engine:

```ts
// Em vez de:
// const result = await processVideoFileWithShielding(...)

// Use:
import { submitToAurelia, getAureliaStatus, downloadFromAurelia } from "@/server/aurelia/client";

// 1. Baixar arquivo do Supabase Storage
const fileBuffer = await downloadFromStorage(bucket, objectPath);

// 2. Enviar para Aurelia
const job = await submitToAurelia({
  fileBuffer,
  filename: originalFilename,
  category: "general",
  strategy: "dual",
});

// 3. Polling até completar
let status = await getAureliaStatus(job.job_id);
while (status.status === "queued" || status.status === "processing") {
  await new Promise(r => setTimeout(r, 2000));
  status = await getAureliaStatus(job.job_id);
}

// 4. Baixar resultado e subir no Supabase
if (status.status === "completed") {
  const processedBuffer = await downloadFromAurelia(job.job_id);
  // Upload para Supabase Storage "processed" bucket...
}
```

---

## Comandos Úteis

```bash
# Ver logs
docker compose logs -f aurelia

# Restart
docker compose restart

# Rebuild após mudanças
docker compose up -d --build

# Ver recursos
docker stats aurelia-engine

# Entrar no container
docker compose exec aurelia bash
```

---

## Estrutura do Projeto

```
aurelia-engine/
├── app/
│   ├── aurelia.py          # Motor de processamento (seu código original)
│   └── main.py             # FastAPI wrapper (API REST)
├── nginx/
│   └── aurelia.conf        # Config Nginx (reverse proxy + SSL)
├── docker-compose.yml      # Orquestração Docker
├── Dockerfile              # Imagem Docker
├── requirements.txt        # Deps Python
├── setup-vps.sh            # Script de setup automático
├── .env.example            # Template de variáveis
└── .gitignore
```
