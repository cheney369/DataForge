# DataForge Milvus Standalone

This development deployment is pinned to Milvus `v2.6.21` and follows the
official standalone topology: Milvus, etcd and MinIO.

```bash
docker compose -f infra/milvus/docker-compose.yml up -d
docker compose -f infra/milvus/docker-compose.yml ps
```

- Milvus: `http://127.0.0.1:19530`
- Milvus WebUI/health: `http://127.0.0.1:9091`
- MinIO console: `http://127.0.0.1:9001`

The default MinIO credentials in this file are intended only for local
development. Production must use protected storage credentials, persistent
volumes, backups and network access controls.
