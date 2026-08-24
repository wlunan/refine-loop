<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent } from 'echarts/components'
use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, MarkLineComponent])
interface RoundData { round: number; score: number }
const props = defineProps<{ data: RoundData[] }>()
const option = computed(() => ({
  tooltip: { trigger: 'axis', backgroundColor: 'rgba(17,24,39,0.9)', borderColor: 'transparent', textStyle: { color: '#fff', fontSize: 12 }, formatter: (p: any) => '第 ' + p[0].name + ' 轮 - ' + p[0].value + ' 分' },
  grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
  xAxis: { type: 'category', data: props.data.map(d => ''+d.round), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
  yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
  series: [{ type: 'line', data: props.data.map(d => d.score), smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2.5, color: '#6366f1' }, itemStyle: { color: '#6366f1', borderWidth: 2, borderColor: '#fff' }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99,102,241,0.15)' }, { offset: 1, color: 'rgba(99,102,241,0.02)' }] } }, markLine: { silent: true, data: [{ yAxis: 85, lineStyle: { color: '#22c55e', type: 'dashed', width: 1 }, label: { show: false } }] } }]
}))
</script>
<template>
  <div class="cw"><v-chart v-if="data.length>0" :option="option" :autoresize="true" style="height:200px;width:100%;" /><div v-else class="ce"><span>暂无数据</span></div></div>
</template>
<style scoped>
.cw{width:100%}.ce{height:200px;display:flex;align-items:center;justify-content:center;color:var(--c-text-3);font-size:var(--text-sm)}
</style>
