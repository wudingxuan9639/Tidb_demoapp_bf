<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from './api'
import type { DatabaseTableRows, ImportResult, ImportTarget } from './types'

const fileInput = ref<HTMLInputElement>()
const selectedFile = ref<File | null>(null)
const importing = ref(false)
const dragActive = ref(false)
const importResult = ref<ImportResult | null>(null)
const importTargets = ref<ImportTarget[]>([])
const targetTable = ref('order_imports')
const databaseTables = ref<string[]>([])
const selectedDatabaseTable = ref('')
const databaseRows = ref<DatabaseTableRows | null>(null)
const databaseLoading = ref(false)
const databaseError = ref('')
const selectedRowIds = ref<number[]>([])
let events: EventSource | undefined

const canDeleteRows = computed(() => importTargets.value.some((target) => target.name === selectedDatabaseTable.value))
const allRowsSelected = computed(() => {
  const rows = databaseRows.value?.rows ?? []
  return rows.length > 0 && rows.every((row) => selectedRowIds.value.includes(Number(row.id)))
})

function chooseFile() {
  fileInput.value?.click()
}

function selectFile(file: File | undefined) {
  if (!file) return
  selectedFile.value = file
  importResult.value = null
}

function handleFileChange(event: Event) {
  selectFile((event.target as HTMLInputElement).files?.[0])
}

function handleDrop(event: DragEvent) {
  dragActive.value = false
  selectFile(event.dataTransfer?.files[0])
}

async function importFile() {
  if (!selectedFile.value) return
  importing.value = true
  importResult.value = null
  try {
    importResult.value = await api.importOrders(selectedFile.value, targetTable.value)
    if (importResult.value.status === 'success') {
      await loadDatabaseMetadata()
      selectedDatabaseTable.value = targetTable.value
      await loadDatabaseRows()
    }
  } catch (reason) {
    importResult.value = {
      status: 'write_failed',
      message: reason instanceof Error ? reason.message : '上传请求失败，请确认后端服务是否正常。',
      total_rows: 0,
      inserted_rows: 0,
      errors: [],
      target_table: targetTable.value,
    }
  } finally {
    importing.value = false
  }
}

async function loadDatabaseMetadata() {
  databaseError.value = ''
  try {
    const [tables, targets] = await Promise.all([api.listDatabaseTables(), api.listImportTargets()])
    databaseTables.value = tables
    importTargets.value = targets
    if (!targets.some((target) => target.name === targetTable.value)) targetTable.value = targets[0]?.name ?? ''
    if (!selectedDatabaseTable.value && tables.length) selectedDatabaseTable.value = tables[0]
  } catch (reason) {
    databaseError.value = reason instanceof Error ? reason.message : '无法读取数据库表列表'
  }
}

async function loadDatabaseRows() {
  if (!selectedDatabaseTable.value) return
  databaseLoading.value = true
  databaseError.value = ''
  selectedRowIds.value = []
  try {
    databaseRows.value = await api.listTableRows(selectedDatabaseTable.value)
  } catch (reason) {
    databaseError.value = reason instanceof Error ? reason.message : '无法读取数据表'
  } finally {
    databaseLoading.value = false
  }
}

function rowId(row: Record<string, unknown>) {
  const id = Number(row.id)
  return Number.isInteger(id) && id > 0 ? id : null
}

function toggleRow(id: number, checked: boolean) {
  selectedRowIds.value = checked
    ? [...new Set([...selectedRowIds.value, id])]
    : selectedRowIds.value.filter((selectedId) => selectedId !== id)
}

function toggleAllRows(checked: boolean) {
  selectedRowIds.value = checked
    ? (databaseRows.value?.rows.map(rowId).filter((id): id is number => id !== null) ?? [])
    : []
}

async function deleteSelectedRows() {
  if (!selectedDatabaseTable.value || selectedRowIds.value.length === 0) return
  if (!window.confirm(`确定删除选中的 ${selectedRowIds.value.length} 条数据吗？此操作不能撤销。`)) return
  databaseLoading.value = true
  databaseError.value = ''
  try {
    await api.deleteTableRows(selectedDatabaseTable.value, selectedRowIds.value)
    await loadDatabaseRows()
  } catch (reason) {
    databaseError.value = reason instanceof Error ? reason.message : '删除数据失败'
  } finally {
    databaseLoading.value = false
  }
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

watch(selectedDatabaseTable, loadDatabaseRows)

onMounted(() => {
  loadDatabaseMetadata()
  events = new EventSource(`${api.apiBase}/api/events`)
  events.addEventListener('database_changed', loadDatabaseRows)
})

onBeforeUnmount(() => events?.close())
</script>

<template>
  <main class="page-shell">
    <header>
      <p class="eyebrow">Vue 3 + FastAPI + TiDB</p>
      <h1>订单数据管理</h1>
    </header>

    <section class="panel import-panel" aria-label="导入订单数据">
      <div class="import-heading">
        <div><h2>导入订单 Excel</h2><p>表头和字段顺序必须与模板完全一致。</p></div>
        <a class="template-link" :href="api.orderTemplateUrl">下载模板</a>
      </div>
      <input ref="fileInput" class="file-input" type="file" accept=".xlsx,.xls" @change="handleFileChange" />
      <div class="drop-zone" :class="{ active: dragActive }" @dragenter.prevent="dragActive = true" @dragover.prevent="dragActive = true" @dragleave.prevent="dragActive = false" @drop.prevent="handleDrop">
        <strong>拖拽 Excel 文件到此处</strong>
        <span>支持 .xlsx 和 .xls，单个文件不超过 5 MB，最多 500 条数据</span>
        <button type="button" @click="chooseFile">浏览本地文件</button>
      </div>
      <div v-if="selectedFile" class="file-summary"><span>{{ selectedFile.name }}</span><span>{{ Math.ceil(selectedFile.size / 1024) }} KB</span><button type="button" class="secondary" :disabled="importing" @click="importFile">{{ importing ? '解析并写库中...' : '开始导入' }}</button></div>
      <label class="target-select">写入目标表<select v-model="targetTable"><option v-for="target in importTargets" :key="target.name" :value="target.name">{{ target.label }}（{{ target.name }}）</option></select></label>
      <div v-if="importResult" class="import-result" :class="importResult.status">
        <strong>{{ importResult.message }}</strong>
        <p v-if="importResult.status === 'success'">已成功写入 {{ importResult.inserted_rows }} 条数据至 {{ importResult.target_table }}。</p>
        <ul v-if="importResult.errors.length">
          <li v-for="(issue, index) in importResult.errors" :key="index">{{ issue.row ? `第 ${issue.row} 行：` : '' }}{{ issue.field ? `${issue.field} - ` : '' }}{{ issue.message }}</li>
        </ul>
      </div>
    </section>

    <section class="panel database-panel" aria-label="TiDB 数据表查询">
      <div class="database-heading"><div><h2>TiDB 数据表查询</h2><p>从当前数据库选择任意表，最多显示 100 行。</p></div><div class="database-actions"><button v-if="canDeleteRows" type="button" class="delete" :disabled="selectedRowIds.length === 0 || databaseLoading" @click="deleteSelectedRows">删除选中（{{ selectedRowIds.length }}）</button><button type="button" class="secondary" @click="loadDatabaseMetadata">刷新表列表</button></div></div>
      <label class="target-select">查询数据表<select v-model="selectedDatabaseTable"><option v-for="table in databaseTables" :key="table" :value="table">{{ table }}</option></select></label>
      <p v-if="databaseError" class="error">{{ databaseError }}</p>
      <p v-else-if="databaseLoading" class="empty">查询中...</p>
      <p v-else-if="databaseRows && databaseRows.rows.length === 0" class="empty">该表暂无数据</p>
      <div v-else-if="databaseRows" class="table-wrap database-table-wrap"><table><thead><tr><th v-if="canDeleteRows" class="selection-column"><input type="checkbox" :checked="allRowsSelected" aria-label="全选数据" @change="toggleAllRows(($event.target as HTMLInputElement).checked)" /></th><th v-for="column in databaseRows.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in databaseRows.rows" :key="index"><td v-if="canDeleteRows" class="selection-column"><input v-if="rowId(row)" type="checkbox" :checked="selectedRowIds.includes(rowId(row)!)" :aria-label="`选择第 ${index + 1} 条数据`" @change="toggleRow(rowId(row)!, ($event.target as HTMLInputElement).checked)" /></td><td v-for="column in databaseRows.columns" :key="column">{{ displayValue(row[column]) }}</td></tr></tbody></table></div>
    </section>

  </main>
</template>
