<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from './api'
import { orderDisplayColumns } from './order-display'
import type { DatabaseTableRows, ImportResult } from './types'

const fileInput = ref<HTMLInputElement>()
const selectedFile = ref<File | null>(null)
const importing = ref(false)
const dragActive = ref(false)
const importResult = ref<ImportResult | null>(null)
const databases = ref<string[]>([])
const targetDatabase = ref('')
const targetTables = ref<string[]>([])
const targetTable = ref('')
const newTableName = ref('')
const creatingTable = ref(false)
const createTableError = ref('')
const selectedDatabase = ref('')
const databaseTables = ref<string[]>([])
const selectedDatabaseTable = ref('')
const databaseRows = ref<DatabaseTableRows | null>(null)
const databaseLoading = ref(false)
const databaseError = ref('')
const selectedRowIds = ref<number[]>([])
let events: EventSource | undefined

const canDeleteRows = computed(() => {
  return selectedDatabase.value === databases.value[0]
    && ['order_imports', 'order_import_archive'].includes(selectedDatabaseTable.value)
})
const visibleDatabaseColumns = computed(() => {
  return orderDisplayColumns(databaseRows.value?.columns ?? [])
})
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

async function importFile(replaceExisting = false) {
  if (!selectedFile.value) return
  importing.value = true
  importResult.value = null
  try {
    importResult.value = await api.importOrders(
      selectedFile.value,
      targetDatabase.value,
      targetTable.value,
      replaceExisting,
    )
    if (importResult.value.status === 'success') {
      selectedDatabase.value = targetDatabase.value
      selectedDatabaseTable.value = targetTable.value
      await refreshDatabaseMetadata()
    }
  } catch (reason) {
    importResult.value = {
      status: 'write_failed',
      message: reason instanceof Error ? reason.message : '上传请求失败，请确认后端服务是否正常。',
      total_rows: 0,
      inserted_rows: 0,
      errors: [],
      target_table: targetTable.value ? `${targetDatabase.value}.${targetTable.value}` : null,
      duplicate_order_ids: [],
      replaced_rows: 0,
    }
  } finally {
    importing.value = false
  }
}

function cancelImport() {
  selectedFile.value = null
  importResult.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function loadDatabases() {
  databaseError.value = ''
  try {
    databases.value = await api.listDatabases()
    if (!databases.value.includes(targetDatabase.value)) targetDatabase.value = databases.value[0] ?? ''
    if (!databases.value.includes(selectedDatabase.value)) selectedDatabase.value = databases.value[0] ?? ''
  } catch (reason) {
    databaseError.value = reason instanceof Error ? reason.message : '无法读取业务数据库列表'
  }
}

async function loadTargetTables() {
  if (!targetDatabase.value) {
    targetTables.value = []
    targetTable.value = ''
    return
  }
  createTableError.value = ''
  try {
    targetTables.value = await api.listSchemaTables(targetDatabase.value)
    if (!targetTables.value.includes(targetTable.value)) targetTable.value = targetTables.value[0] ?? ''
  } catch (reason) {
    targetTables.value = []
    targetTable.value = ''
    createTableError.value = reason instanceof Error ? reason.message : '无法读取写入目标表'
  }
}

async function loadQueryTables() {
  if (!selectedDatabase.value) {
    databaseTables.value = []
    selectedDatabaseTable.value = ''
    databaseRows.value = null
    return
  }
  databaseLoading.value = true
  databaseError.value = ''
  try {
    databaseTables.value = await api.listSchemaTables(selectedDatabase.value)
    if (!databaseTables.value.includes(selectedDatabaseTable.value)) selectedDatabaseTable.value = databaseTables.value[0] ?? ''
    if (!selectedDatabaseTable.value) databaseRows.value = null
  } catch (reason) {
    databaseTables.value = []
    selectedDatabaseTable.value = ''
    databaseRows.value = null
    databaseError.value = reason instanceof Error ? reason.message : '无法读取数据库表列表'
  } finally {
    databaseLoading.value = false
  }
}

async function loadDatabaseRows() {
  if (!selectedDatabaseTable.value) return
  databaseLoading.value = true
  databaseError.value = ''
  selectedRowIds.value = []
  try {
    databaseRows.value = await api.listSchemaTableRows(selectedDatabase.value, selectedDatabaseTable.value)
  } catch (reason) {
    databaseError.value = reason instanceof Error ? reason.message : '无法读取数据表'
  } finally {
    databaseLoading.value = false
  }
}

async function refreshDatabaseMetadata() {
  await loadDatabases()
  await Promise.all([loadTargetTables(), loadQueryTables()])
  await loadDatabaseRows()
}

async function createTargetTable() {
  if (!targetDatabase.value || !newTableName.value.trim()) return
  creatingTable.value = true
  createTableError.value = ''
  try {
    const result = await api.createOrderImportTable(targetDatabase.value, newTableName.value.trim())
    newTableName.value = ''
    await loadTargetTables()
    targetTable.value = result.table
    selectedDatabase.value = result.database
    selectedDatabaseTable.value = result.table
    await loadQueryTables()
  } catch (reason) {
    createTableError.value = reason instanceof Error ? reason.message : '新建数据表失败'
  } finally {
    creatingTable.value = false
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

watch(targetDatabase, loadTargetTables)
watch(selectedDatabase, loadQueryTables)
watch(selectedDatabaseTable, loadDatabaseRows)

onMounted(() => {
  refreshDatabaseMetadata()
  events = new EventSource(`${api.apiBase}/api/events`)
  events.addEventListener('database_changed', refreshDatabaseMetadata)
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
      <div class="query-selects">
        <label class="target-select">写入目标数据库<select v-model="targetDatabase"><option v-for="database in databases" :key="database" :value="database">{{ database }}</option></select></label>
        <label class="target-select">写入目标表<select v-model="targetTable" :disabled="targetTables.length === 0"><option v-for="table in targetTables" :key="table" :value="table">{{ table }}</option></select></label>
      </div>
      <div v-if="targetDatabase && targetTables.length === 0" class="new-table-form">
        <p>当前数据库没有数据表。新建表后可直接按订单模板导入。</p>
        <div><input v-model="newTableName" maxlength="64" placeholder="例如：orders_2026" /><button type="button" :disabled="creatingTable || !newTableName.trim()" @click="createTargetTable">{{ creatingTable ? '新建中...' : '新建数据表' }}</button></div>
        <p v-if="createTableError" class="error">{{ createTableError }}</p>
      </div>
      <div v-if="selectedFile" class="file-summary"><span>{{ selectedFile.name }}</span><span>{{ Math.ceil(selectedFile.size / 1024) }} KB</span><button type="button" class="secondary" :disabled="importing || !targetDatabase || !targetTable" @click="() => importFile()">{{ importing ? '解析并写库中...' : '开始导入' }}</button></div>
      <div v-if="importResult" class="import-result" :class="importResult.status">
        <strong>{{ importResult.message }}</strong>
        <p v-if="importResult.status === 'success'">已成功写入 {{ importResult.inserted_rows }} 条数据至 {{ importResult.target_table }}<template v-if="importResult.replaced_rows">，其中替换已有订单 {{ importResult.replaced_rows }} 条</template>。</p>
        <template v-else-if="importResult.status === 'duplicate_conflict'">
          <p>发现 {{ importResult.duplicate_order_ids.length }} 个订单 ID 已存在：{{ importResult.duplicate_order_ids.join('、') }}。</p>
          <div class="replacement-actions"><button type="button" :disabled="importing" @click="importFile(true)">是，替换已有数据</button><button type="button" class="secondary" :disabled="importing" @click="cancelImport">否，取消本次上传</button></div>
        </template>
        <ul v-if="importResult.errors.length">
          <li v-for="(issue, index) in importResult.errors" :key="index">{{ issue.row ? `第 ${issue.row} 行：` : '' }}{{ issue.field ? `${issue.field} - ` : '' }}{{ issue.message }}</li>
        </ul>
      </div>
    </section>

    <section class="panel database-panel" aria-label="TiDB 数据表查询">
      <div class="database-heading"><div><h2>TiDB 数据表查询</h2><p>选择业务数据库和数据表，最多显示 100 行。</p></div><div class="database-actions"><button v-if="canDeleteRows" type="button" class="delete" :disabled="selectedRowIds.length === 0 || databaseLoading" @click="deleteSelectedRows">删除选中（{{ selectedRowIds.length }}）</button><button type="button" class="secondary" :disabled="databaseLoading" @click="refreshDatabaseMetadata">刷新数据库列表</button></div></div>
      <div class="query-selects">
        <label class="target-select">查询数据库<select v-model="selectedDatabase"><option v-for="database in databases" :key="database" :value="database">{{ database }}</option></select></label>
        <label class="target-select">查询数据表<select v-model="selectedDatabaseTable" :disabled="databaseTables.length === 0"><option v-for="table in databaseTables" :key="table" :value="table">{{ table }}</option></select></label>
      </div>
      <p class="query-context">当前查询：<strong>{{ selectedDatabase || '-' }}</strong> / <strong>{{ selectedDatabaseTable || '-' }}</strong></p>
      <p v-if="databaseError" class="error">{{ databaseError }}</p>
      <p v-else-if="databaseLoading" class="empty">查询中...</p>
      <p v-else-if="selectedDatabase && databaseTables.length === 0" class="empty">该数据库暂无数据表，请在上方导入区域新建订单导入表。</p>
      <p v-else-if="databaseRows && databaseRows.rows.length === 0" class="empty">该表暂无数据</p>
      <div v-else-if="databaseRows" class="table-wrap database-table-wrap"><table><thead><tr><th v-if="canDeleteRows" class="selection-column"><input type="checkbox" :checked="allRowsSelected" aria-label="全选数据" @change="toggleAllRows(($event.target as HTMLInputElement).checked)" /></th><th v-for="column in visibleDatabaseColumns" :key="column.source">{{ column.label }}</th></tr></thead><tbody><tr v-for="(row, index) in databaseRows.rows" :key="index"><td v-if="canDeleteRows" class="selection-column"><input v-if="rowId(row)" type="checkbox" :checked="selectedRowIds.includes(rowId(row)!)" :aria-label="`选择第 ${index + 1} 条数据`" @change="toggleRow(rowId(row)!, ($event.target as HTMLInputElement).checked)" /></td><td v-for="column in visibleDatabaseColumns" :key="column.source">{{ displayValue(row[column.source]) }}</td></tr></tbody></table></div>
    </section>

  </main>
</template>
