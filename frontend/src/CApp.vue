<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from './api'
import type { PaginatedOrderRows } from './types'

type SortBy = 'order_id' | 'order_date'
type SearchField = 'order_id' | 'customer_name' | 'amount'

const sortBy = ref<SortBy>('order_id')
const searchField = ref<SearchField>('order_id')
const keyword = ref('')
const page = ref(1)
const orders = ref<PaginatedOrderRows | null>(null)
const loading = ref(false)
const error = ref('')
let requestVersion = 0
let events: EventSource | undefined

function displayAmount(value: string | number) {
  const amount = Number(value)
  return Number.isFinite(amount) ? `¥${amount.toFixed(2)}` : `¥${value}`
}

async function loadOrders() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const result = await api.listAllOrders(page.value, sortBy.value, searchField.value, keyword.value)
    if (version !== requestVersion) return
    if (page.value > result.total_pages) {
      page.value = result.total_pages
      await loadOrders()
      return
    }
    orders.value = result
  } catch (reason) {
    if (version !== requestVersion) return
    orders.value = null
    error.value = reason instanceof Error ? reason.message : '无法读取订单数据'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function selectSort(value: SortBy) {
  if (sortBy.value === value) return
  sortBy.value = value
  page.value = 1
  loadOrders()
}

function searchOrders() {
  page.value = 1
  loadOrders()
}

function changePage(nextPage: number) {
  page.value = nextPage
  loadOrders()
}

onMounted(() => {
  loadOrders()
  events = new EventSource(`${api.apiBase}/api/events`)
  events.addEventListener('database_changed', loadOrders)
})

onBeforeUnmount(() => events?.close())
</script>

<template>
  <main class="page-shell c-page">
    <header>
      <p class="eyebrow">C 端 · 订单浏览</p>
      <h1>订单信息</h1>
    </header>

    <section class="c-orders" aria-label="全部订单">
      <div class="c-toolbar">
        <div class="sort-control" aria-label="订单排序">
          <button type="button" :class="{ active: sortBy === 'order_id' }" @click="selectSort('order_id')">按订单 ID 排序</button>
          <button type="button" :class="{ active: sortBy === 'order_date' }" @click="selectSort('order_date')">按下单日期排序</button>
        </div>
        <button type="button" class="icon-button" title="刷新订单" aria-label="刷新订单" :disabled="loading" @click="loadOrders">↻</button>
      </div>

      <form class="order-search" @submit.prevent="searchOrders">
        <label>查询字段
          <select v-model="searchField">
            <option value="order_id">订单 ID</option>
            <option value="amount">订单金额</option>
            <option value="customer_name">客户名称</option>
          </select>
        </label>
        <label class="search-keyword">查询内容
          <input v-model="keyword" :placeholder="searchField === 'amount' ? '例如：1288.50' : '输入关键字'" />
        </label>
        <button type="submit" :disabled="loading">查询</button>
        <button v-if="keyword" type="button" class="secondary" :disabled="loading" @click="keyword = ''; searchOrders()">清除</button>
      </form>

      <p v-if="error" class="error">{{ error }}</p>
      <p v-else-if="loading && !orders" class="empty">查询中...</p>
      <p v-else-if="orders && orders.rows.length === 0" class="empty">没有符合条件的订单数据</p>
      <div v-else-if="orders" class="order-card-grid">
        <article v-for="order in orders.rows" :key="`${order.order_id}-${order.order_date}-${order.customer_name}`" class="order-card">
          <h2>{{ order.order_id }}</h2>
          <img src="/order-card-image.png" alt="订单服务场景" />
          <div class="order-card-body">
            <p class="customer-name">{{ order.customer_name }}</p>
            <div class="order-meta"><span>{{ displayAmount(order.amount) }}</span><time>{{ order.order_date }}</time></div>
          </div>
        </article>
      </div>

      <div v-if="orders && orders.total > 0" class="pagination">
        <button type="button" class="secondary" :disabled="loading || page <= 1" @click="changePage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ orders.total_pages }} 页，共 {{ orders.total }} 条</span>
        <button type="button" class="secondary" :disabled="loading || page >= orders.total_pages" @click="changePage(page + 1)">下一页</button>
      </div>
    </section>
  </main>
</template>
