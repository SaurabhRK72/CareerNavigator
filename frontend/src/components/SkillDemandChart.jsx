import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js/lib/core'
import bar from 'plotly.js/lib/bar'

Plotly.register([bar])
const Plot = createPlotlyComponent(Plotly)

function SkillDemandChart({ skills }) {
  const skillLabels = skills.map((item) => item.skill)
  const skillValues = skills.map((item) => item.demand_percentage)

  return (
    <Plot
      data={[
        {
          type: 'bar',
          orientation: 'h',
          x: skillValues,
          y: skillLabels,
          marker: { color: '#248c83' },
          text: skillValues.map((value) => `${value}%`),
          textposition: 'outside',
          cliponaxis: false,
          hovertemplate:
            '%{y}<br>%{x:.2f}% of unique jobs<extra></extra>',
        },
      ]}
      layout={{
        autosize: true,
        height: Math.max(260, skillLabels.length * 38),
        margin: { l: 110, r: 42, t: 12, b: 38 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: 'Inter, sans-serif', color: '#536276', size: 11 },
        xaxis: {
          title: {
            text: 'Share of unique job postings',
            font: { size: 10 },
          },
          range: [0, Math.min(100, Math.max(...skillValues, 10) * 1.25)],
          ticksuffix: '%',
          gridcolor: '#edf1f2',
          zeroline: false,
        },
        yaxis: { autorange: 'reversed', automargin: true },
        showlegend: false,
      }}
      config={{ displayModeBar: false, responsive: true }}
      useResizeHandler
      style={{ width: '100%' }}
    />
  )
}

export default SkillDemandChart
