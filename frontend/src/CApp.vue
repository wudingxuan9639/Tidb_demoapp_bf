<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from './api'
import { orderDisplayColumns } from './order-display'
import type { DatabaseTableRows } from './types'

const databases = ref<string[]>([])
const tables = ref<string[]>([])
const selectedDatabase = ref('')
const selectedTable = ref('')
const rows = ref<DatabaseTableRows | null>(null)
const loading = ref(false)
const error = ref('')
let events: EventSource | undefined

const visibleColumns = computed(() => orderDisplayColumns(rows.value?.columns ?? []))

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

async function loadRows() {
  if (!selectedDatabase.value || !selectedTable.value) {
    rows.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    rows.value = await api.listSchemaTableRows(selectedDatabase.value, selectedTable.value)
  } catch (reason) {
    rows.value = null
    error.value = reason instanceof Error ? reason.message : '无法读取数据表'
  } finally {
    loading.value = false
  }
}

async function loadTables() {
  if (!selectedDatabase.value) {
    tables.value = []
    selectedTable.value = ''
    rows.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    tables.value = await api.listSchemaTables(selectedDatabase.value)
    if (!tables.value.includes(selectedTable.value)) selectedTable.value = tables.value[0] ?? ''
    if (!selectedTable.value) rows.value = null
  } catch (reason) {
    tables.value = []
    selectedTable.value = ''
    rows.value = null
    error.value = reason instanceof Error ? reason.message : '无法读取数据库表列表'
  } finally {
    loading.value = false
  }
}

async function refreshDatabaseMetadata() {
  loading.value = true
  error.value = ''
  try {
    databases.value = await api.listDatabases()
    if (!databases.value.includes(selectedDatabase.value)) selectedDatabase.value = databases.value[0] ?? ''
    await loadTables()
    await loadRows()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取 TiDB 数据库列表'
  } finally {
    loading.value = false
  }
}

watch(selectedDatabase, loadTables)
watch(selectedTable, loadRows)

onMounted(() => {
  refreshDatabaseMetadata()
  events = new EventSource(`${api.apiBase}/api/events`)
  events.addEventListener('database_changed', refreshDatabaseMetadata)
})

onBeforeUnmount(() => events?.close())
</script>

<template>
  <main class="page-shell c-page">
    <header>
      <p class="eyebrow">C 端 · TiDB 数据库浏览</p>
      <h1>数据库查询</h1>
    </header>

    <section class="panel database-panel" aria-label="TiDB 数据库查询">
      <div class="database-heading">
        <div>
          <h2>TiDB 数据库浏览</h2>
          <p>选择数据库和数据表，最多显示 100 行。</p>
        </div>
        <button type="button" class="secondary" :disabled="loading" @click="refreshDatabaseMetadata">刷新</button>
      </div>

      <div class="query-selects">
        <label class="target-select">数据库
          <select v-model="selectedDatabase" :disabled="loading"><option v-for="database in databases" :key="database" :value="database">{{ database }}</option></select>
        </label>
        <label class="target-select">数据表
          <select v-model="selectedTable" :disabled="loading || !selectedDatabase"><option v-for="table in tables" :key="table" :value="table">{{ table }}</option></select>
        </label>
      </div>

      <p class="query-context">当前查询：<strong>{{ selectedDatabase || '-' }}</strong> / <strong>{{ selectedTable || '-' }}</strong></p>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-else-if="loading" class="empty">查询中...</p>
      <p v-else-if="selectedDatabase && tables.length === 0" class="empty">该数据库暂无数据表</p>
      <p v-else-if="rows && rows.rows.length === 0" class="empty">该表暂无数据</p>
      <div v-else-if="rows" class="table-wrap database-table-wrap">
        <table>
          <thead><tr><th v-for="column in visibleColumns" :key="column.source">{{ column.label }}</th></tr></thead>
          <tbody><tr v-for="(row, index) in rows.rows" :key="index"><td v-for="column in visibleColumns" :key="column.source">{{ displayValue(row[column.source]) }}</td></tr></tbody>
        </table>
      </div>
    </section>
  </main>
</template>
