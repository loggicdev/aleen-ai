#!/bin/bash
# wait-for-redis.sh - Script para aguardar o Redis estar pronto

set -e

host="$1"
port="$2"
shift 2
cmd="$@"

until nc -z "$host" "$port"; do
  >&2 echo "🔄 Redis não está pronto em $host:$port - aguardando..."
  sleep 2
done

>&2 echo "✅ Redis está pronto em $host:$port - executando comando"
exec $cmd
