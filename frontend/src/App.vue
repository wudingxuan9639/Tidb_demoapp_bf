<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from './api'
import type { ImportResult, OrderInput, OrderRow, PaginatedOrderRows } from './types'

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
const databaseRows = ref<PaginatedOrderRows | null>(null)
const databaseLoading = ref(false)
const databaseError = ref('')
const selectedOrderIds = ref<string[]>([])
const page = ref(1)
const editorOpen = ref(false)
const editorMode = ref<'create' | 'edit'>('create')
const editorLoading = ref(false)
const editorError = ref('')
const editorForm = ref<OrderInput>({ order_id: '', customer_name: '', amount: '', order_date: '' })
const pendingDuplicate = ref(false)
let events: EventSource | undefined

const allRowsSelected = computed(() => {
  const rows = databaseRows.value?.rows ?? []
  return rows.length > 0 && rows.every((row) => selectedOrderIds.value.includes(row.order_id))
})

function chooseFile() { fileInput.value?.click() }
function selectFile(file: File | undefined) { if (file) { selectedFile.value = file; importResult.value = null } }
function handleFileChange(event: Event) { selectFile((event.target as HTMLInputElement).files?.[0]) }
function handleDrop(event: DragEvent) { dragActive.value = false; selectFile(event.dataTransfer?.files[0]) }

async function importFile(replaceExisting = false) {
  if (!selectedFile.value) return
  importing.value = true
  importResult.value = null
  try {
    importResult.value = await api.importOrders(selectedFile.value, targetDatabase.value, targetTable.value, replaceExisting)
    if (importResult.value.status === 'success') {
      selectedDatabase.value = targetDatabase.value
      selectedDatabaseTable.value = targetTable.value
      page.value = 1
      await refreshDatabaseMetadata()
    }
  } catch (reason) {
    importResult.value = { status: 'write_failed', message: reason instanceof Error ? reason.message : '上传请求失败，请确认后端服务是否正常。', total_rows: 0, inserted_rows: 0, errors: [], target_table: targetTable.value ? `${targetDatabase.value}.${targetTable.value}` : null, duplicate_order_ids: [], replaced_rows: 0 }
  } finally { importing.value = false }
}

function cancelImport() { selectedFile.value = null; importResult.value = null; if (fileInput.value) fileInput.value.value = '' }

async function loadDatabases() {
  databaseError.value = ''
  try {
    databases.value = await api.listDatabases()
    if (!databases.value.includes(targetDatabase.value)) targetDatabase.value = databases.value[0] ?? ''
    if (!databases.value.includes(selectedDatabase.value)) selectedDatabase.value = databases.value[0] ?? ''
  } catch (reason) { databaseError.value = reason instanceof Error ? reason.message : '无法读取业务数据库列表' }
}

async function loadTargetTables() {
  if (!targetDatabase.value) { targetTables.value = []; targetTable.value = ''; return }
  createTableError.value = ''
  try {
    targetTables.value = await api.listSchemaTables(targetDatabase.value)
    if (!targetTables.value.includes(targetTable.value)) targetTable.value = targetTables.value[0] ?? ''
  } catch (reason) { targetTables.value = []; targetTable.value = ''; createTableError.value = reason instanceof Error ? reason.message : '无法读取写入目标表' }
}

async function loadQueryTables() {
  if (!selectedDatabase.value) { databaseTables.value = []; selectedDatabaseTable.value = ''; databaseRows.value = null; return }
  try {
    databaseTables.value = await api.listSchemaTables(selectedDatabase.value)
    if (!databaseTables.value.includes(selectedDatabaseTable.value)) selectedDatabaseTable.value = databaseTables.value[0] ?? ''
    if (!selectedDatabaseTable.value) databaseRows.value = null
  } catch (reason) { databaseTables.value = []; selectedDatabaseTable.value = ''; databaseRows.value = null; databaseError.value = reason instanceof Error ? reason.message : '无法读取数据库表列表' }
}

async function loadDatabaseRows() {
  if (!selectedDatabase.value || !selectedDatabaseTable.value) { databaseRows.value = null; return }
  databaseLoading.value = true
  databaseError.value = ''
  selectedOrderIds.value = []
  try {
    const rows = await api.listSchemaOrders(selectedDatabase.value, selectedDatabaseTable.value, page.value)
    if (page.value > rows.total_pages) { page.value = rows.total_pages; return }
    databaseRows.value = rows
  } catch (reason) { databaseRows.value = null; databaseError.value = reason instanceof Error ? reason.message : '当前数据表不符合订单数据结构' }
  finally { databaseLoading.value = false }
}

async function refreshDatabaseMetadata() { await loadDatabases(); await Promise.all([loadTargetTables(), loadQueryTables()]); await loadDatabaseRows() }

async function createTargetTable() {
  if (!targetDatabase.value || !newTableName.value.trim()) return
  creatingTable.value = true; createTableError.value = ''
  try {
    const result = await api.createOrderImportTable(targetDatabase.value, newTableName.value.trim())
    newTableName.value = ''
    await loadTargetTables(); targetTable.value = result.table; selectedDatabase.value = result.database; selectedDatabaseTable.value = result.table; page.value = 1
    await loadQueryTables(); await loadDatabaseRows()
  } catch (reason) { createTableError.value = reason instanceof Error ? reason.message : '新建数据表失败' }
  finally { creatingTable.value = false }
}

function toggleRow(orderId: string, checked: boolean) { selectedOrderIds.value = checked ? [...new Set([...selectedOrderIds.value, orderId])] : selectedOrderIds.value.filter((id) => id !== orderId) }
function toggleAllRows(checked: boolean) { selectedOrderIds.value = checked ? (databaseRows.value?.rows.map((row) => row.order_id) ?? []) : [] }

async function deleteOrders(orderIds: string[]) {
  if (!selectedDatabase.value || !selectedDatabaseTable.value || orderIds.length === 0) return
  if (!window.confirm(`确定删除 ${orderIds.length} 条数据吗？此操作不能撤销。`)) return
  databaseLoading.value = true; databaseError.value = ''
  try { await api.deleteSchemaOrders(selectedDatabase.value, selectedDatabaseTable.value, orderIds); await loadDatabaseRows() }
  catch (reason) { databaseError.value = reason instanceof Error ? reason.message : '删除数据失败' }
  finally { databaseLoading.value = false }
}

function openCreate() { editorMode.value = 'create'; editorError.value = ''; pendingDuplicate.value = false; editorForm.value = { order_id: '', customer_name: '', amount: '', order_date: '' }; editorOpen.value = true }
function openEdit(row: OrderRow) { editorMode.value = 'edit'; editorError.value = ''; editorForm.value = { order_id: row.order_id, customer_name: row.customer_name, amount: String(row.amount), order_date: String(row.order_date).slice(0, 10) }; editorOpen.value = true }
function closeEditor() { if (!editorLoading.value) editorOpen.value = false }

async function saveOrder(replaceExisting = false) {
  if (!selectedDatabase.value || !selectedDatabaseTable.value) return
  editorLoading.value = true; editorError.value = ''
  try {
    const result = editorMode.value === 'create'
      ? await api.createOrder(selectedDatabase.value, selectedDatabaseTable.value, editorForm.value, replaceExisting)
      : await api.updateOrder(selectedDatabase.value, selectedDatabaseTable.value, editorForm.value.order_id, editorForm.value)
    if (result.status === 'duplicate_conflict') { pendingDuplicate.value = true; return }
    editorOpen.value = false; page.value = 1; await loadDatabaseRows()
  } catch (reason) { editorError.value = reason instanceof Error ? reason.message : '保存订单失败' }
  finally { editorLoading.value = false }
}

function displayAmount(value: string | number) { const amount = Number(value); return Number.isFinite(amount) ? amount.toFixed(2) : String(value) }

watch(targetDatabase, loadTargetTables)
watch(selectedDatabase, async () => {
  page.value = 1
  await loadQueryTables()
  await loadDatabaseRows()
})
watch(selectedDatabaseTable, async () => {
  if (page.value !== 1) page.value = 1
  else await loadDatabaseRows()
})
watch(page, loadDatabaseRows)

onMounted(() => { refreshDatabaseMetadata(); events = new EventSource(`${api.apiBase}/api/events`); events.addEventListener('database_changed', refreshDatabaseMetadata) })
onBeforeUnmount(() => events?.close())
</script>

<template>
  <main class="page-shell">
    <header><p class="eyebrow">Vue 3 + FastAPI + TiDB</p><h1>订单数据管理</h1></header>
    <section class="panel import-panel" aria-label="导入订单数据">
      <div class="import-heading"><div><h2>导入订单 Excel</h2><p>表头和字段顺序必须与模板完全一致。</p></div><a class="template-link" :href="api.orderTemplateUrl">下载模板</a></div>
      <input ref="fileInput" class="file-input" type="file" accept=".xlsx,.xls" @change="handleFileChange" />
      <div class="drop-zone" :class="{ active: dragActive }" @dragenter.prevent="dragActive = true" @dragover.prevent="dragActive = true" @dragleave.prevent="dragActive = false" @drop.prevent="handleDrop"><strong>拖拽 Excel 文件到此处</strong><span>支持 .xlsx 和 .xls，单个文件不超过 5 MB，最多 500 条数据</span><button type="button" @click="chooseFile">浏览本地文件</button></div>
      <div class="query-selects"><label class="target-select">写入目标数据库<select v-model="targetDatabase"><option v-for="database in databases" :key="database" :value="database">{{ database }}</option></select></label><label class="target-select">写入目标表<select v-model="targetTable" :disabled="targetTables.length === 0"><option v-for="table in targetTables" :key="table" :value="table">{{ table }}</option></select></label></div>
      <div v-if="targetDatabase && targetTables.length === 0" class="new-table-form"><p>当前数据库没有数据表。新建表后可直接按订单模板导入。</p><div><input v-model="newTableName" maxlength="64" placeholder="例如：orders_2026" /><button type="button" :disabled="creatingTable || !newTableName.trim()" @click="createTargetTable">{{ creatingTable ? '新建中...' : '新建数据表' }}</button></div><p v-if="createTableError" class="error">{{ createTableError }}</p></div>
      <div v-if="selectedFile" class="file-summary"><span>{{ selectedFile.name }}</span><span>{{ Math.ceil(selectedFile.size / 1024) }} KB</span><button type="button" class="secondary" :disabled="importing || !targetDatabase || !targetTable" @click="importFile()">{{ importing ? '解析并写库中...' : '开始导入' }}</button></div>
      <div v-if="importResult" class="import-result" :class="importResult.status"><strong>{{ importResult.message }}</strong><p v-if="importResult.status === 'success'">已成功写入 {{ importResult.inserted_rows }} 条数据至 {{ importResult.target_table }}<template v-if="importResult.replaced_rows">，其中替换已有订单 {{ importResult.replaced_rows }} 条</template>。</p><template v-else-if="importResult.status === 'duplicate_conflict'"><p>发现 {{ importResult.duplicate_order_ids.length }} 个订单 ID 已存在：{{ importResult.duplicate_order_ids.join('、') }}。</p><div class="replacement-actions"><button type="button" :disabled="importing" @click="importFile(true)">是，替换已有数据</button><button type="button" class="secondary" :disabled="importing" @click="cancelImport">否，取消本次上传</button></div></template><ul v-if="importResult.errors.length"><li v-for="(issue, index) in importResult.errors" :key="index">{{ issue.row ? `第 ${issue.row} 行：` : '' }}{{ issue.field ? `${issue.field} - ` : '' }}{{ issue.message }}</li></ul></div>
    </section>

    <section class="panel database-panel" aria-label="TiDB 数据表查询">
      <div class="database-heading"><div><h2>TiDB 数据表查询</h2><p>选择业务数据库和数据表，每页 100 条订单数据。</p></div><div class="database-actions"><button type="button" class="secondary" :disabled="databaseLoading" @click="openCreate">新增数据</button><button type="button" class="secondary" :disabled="databaseLoading" @click="refreshDatabaseMetadata">刷新数据库列表</button></div></div>
      <div class="query-selects"><label class="target-select">查询数据库<select v-model="selectedDatabase"><option v-for="database in databases" :key="database" :value="database">{{ database }}</option></select></label><label class="target-select">查询数据表<select v-model="selectedDatabaseTable" :disabled="databaseTables.length === 0"><option v-for="table in databaseTables" :key="table" :value="table">{{ table }}</option></select></label></div>
      <p class="query-context">当前查询：<strong>{{ selectedDatabase || '-' }}</strong> / <strong>{{ selectedDatabaseTable || '-' }}</strong></p>
      <p v-if="databaseError" class="error">{{ databaseError }}</p><p v-else-if="databaseLoading && !databaseRows" class="empty">查询中...</p><p v-else-if="selectedDatabase && databaseTables.length === 0" class="empty">该数据库暂无数据表，请在上方导入区域新建订单导入表。</p><p v-else-if="databaseRows && databaseRows.rows.length === 0" class="empty">该表暂无数据</p>
      <div v-else-if="databaseRows" class="table-wrap database-table-wrap"><table><thead><tr><th class="selection-column"><input type="checkbox" :checked="allRowsSelected" aria-label="全选数据" @change="toggleAllRows(($event.target as HTMLInputElement).checked)" /></th><th>订单ID</th><th>客户名称</th><th>订单金额</th><th>下单日期</th><th class="row-actions">操作</th></tr></thead><tbody><tr v-for="row in databaseRows.rows" :key="row.order_id"><td class="selection-column"><input type="checkbox" :checked="selectedOrderIds.includes(row.order_id)" :aria-label="`选择订单 ${row.order_id}`" @change="toggleRow(row.order_id, ($event.target as HTMLInputElement).checked)" /></td><td>{{ row.order_id }}</td><td>{{ row.customer_name }}</td><td>{{ displayAmount(row.amount) }}</td><td>{{ row.order_date }}</td><td class="row-actions"><button type="button" class="small-button secondary" @click="openEdit(row)">修改</button><button type="button" class="small-button delete" @click="deleteOrders([row.order_id])">删除</button></td></tr></tbody></table></div>
      <div v-if="databaseRows && databaseRows.total > 0" class="pagination"><button type="button" class="secondary" :disabled="databaseLoading || page <= 1" @click="page -= 1">上一页</button><span>第 {{ page }} / {{ databaseRows.total_pages }} 页，共 {{ databaseRows.total }} 条</span><button type="button" class="secondary" :disabled="databaseLoading || page >= databaseRows.total_pages" @click="page += 1">下一页</button><button type="button" class="delete" :disabled="databaseLoading || selectedOrderIds.length === 0" @click="deleteOrders(selectedOrderIds)">删除选中（{{ selectedOrderIds.length }}）</button></div>
    </section>

    <div v-if="editorOpen" class="modal-backdrop" @click.self="closeEditor"><section class="modal" role="dialog" aria-modal="true" :aria-label="editorMode === 'create' ? '新增数据' : '修改数据'"><div class="modal-heading"><h2>{{ editorMode === 'create' ? '新增数据' : '修改数据' }}</h2><button type="button" class="icon-button" title="关闭" aria-label="关闭" :disabled="editorLoading" @click="closeEditor">X</button></div><label>订单ID<input v-model="editorForm.order_id" :readonly="editorMode === 'edit'" maxlength="64" /></label><label>客户名称<input v-model="editorForm.customer_name" maxlength="100" /></label><label>订单金额<input v-model="editorForm.amount" inputmode="decimal" /></label><label>下单日期<input v-model="editorForm.order_date" type="date" /></label><p v-if="editorError" class="error">{{ editorError }}</p><p v-if="pendingDuplicate" class="duplicate-note">该订单 ID 已存在，是否替换原有业务数据？</p><div class="modal-actions"><template v-if="pendingDuplicate"><button type="button" :disabled="editorLoading" @click="saveOrder(true)">是，替换</button><button type="button" class="secondary" :disabled="editorLoading" @click="closeEditor">否，取消</button></template><template v-else><button type="button" :disabled="editorLoading" @click="saveOrder()">{{ editorLoading ? '保存中...' : '确认保存' }}</button><button type="button" class="secondary" :disabled="editorLoading" @click="closeEditor">取消</button></template></div></section></div>
  </main>
</template>
