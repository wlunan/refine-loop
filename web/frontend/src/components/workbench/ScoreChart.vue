<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
} from 'echarts/components'

use([
  CanvasRenderer,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
])

interface RoundData {
  round: number
  score: number
}

const props = defineProps<{
  data: RoundData[]
}>()

const option = computed(() => ({
  tooltip: {
    trigger: 'axis',
    formatter: (params: any) => {
      const data = params[0]
      return `第 ${data.name} 轮<br/>评分: ${data.value}`
    },
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '3%',
    top: '10%',
    containLabel: true,
  },
  xAxis: {
    type: 'category',
    data: props.data.map((d) => `${d.round}`),
    name: '轮次',
    axisLabel: {
      formatter: (value: string) => `第${value}轮`,
    },
  },
  yAxis: {
    type: 'value',
    name: '评分',
    min: 0,
    max: 100,
    splitLine: {
      lineStyle: {
        type: 'dashed',
      },
    },
  },
  series: [
    {
      name: '评分',
      type: 'line',
      data: props.data.map((d) => d.score),
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      lineStyle: {
        width: 3,
        color: '#6366f1',
      },
      itemStyle: {
        color: '#6366f1',
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(99, 102, 241, 0.3)' },
            { offset: 1, color: 'rgba(99, 102, 241, 0.05)' },
          ],
        },
      },
      markLine: {
        data: [
          {
            yAxis: 85,
            name: '收敛阈值',
            lineStyle: {
              color: '#52c41a',
              type: 'dashed',
            },
            label: {
              formatter: '收敛阈值: 85',
              position: 'end',
            },
          },
        ],
      },
    },
  ],
}))
</script>

<template>
  <div class="chart-container">
    <v-chart
      v-if="data.length > 0"
      :option="option"
      :autoresize="true"
      style="height: 250px;"
    />
    <a-empty v-else description="暂无数据" />
  </div>
</template>

<style scoped>
.chart-container {
  width: 100%;
}
</style>
