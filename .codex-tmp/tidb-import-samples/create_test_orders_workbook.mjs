import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "/Users/liuchangsheng/Documents/Python_demo/.codex-tmp/tidb-import-samples";
const outputPath = `${outputDir}/tidb_test_orders.xlsx`;

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("test_orders");
sheet.showGridLines = false;

sheet.getRange("A1:I1").merge();
sheet.getRange("A1").values = [["TiDB 测试订单导入数据"]];
sheet.getRange("A1:I1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A1:I1").format.rowHeight = 28;

sheet.getRange("A2:I2").merge();
sheet.getRange("A2").values = [["目标库：import_demo    目标表：test_orders    可用于 DBeaver 导入练习"]];
sheet.getRange("A2:I2").format = {
  fill: "#E6F4F1",
  font: { color: "#20574D", italic: true },
  verticalAlignment: "center",
};
sheet.getRange("A2:I2").format.rowHeight = 22;

const rows = [
  ["order_id", "customer_code", "customer_name", "product_name", "quantity", "unit_price", "order_date", "status", "notes"],
  [10001, "C-0001", "张晓明", "无线键盘", 2, 129.0, new Date("2026-08-01T00:00:00"), "已完成", "含中文和文本编号"],
  [10002, "C-0002", "李娜", "显示器支架", 1, 219.5, new Date("2026-08-02T00:00:00"), "待发货", null],
  [10003, "C-0003", "王强", "USB-C 扩展坞", 3, 349.0, new Date("2026-08-03T00:00:00"), "已完成", "加急订单"],
  [10004, "C-0004", "陈雨", "人体工学鼠标", 1, 269.0, new Date("2026-08-04T00:00:00"), "已取消", "客户取消"],
  [10005, "C-0005", "赵敏", "机械键盘", 2, 459.9, new Date("2026-08-05T00:00:00"), "待发货", "请工作日配送"],
];

sheet.getRange("A4:I9").values = rows;
sheet.getRange("A4:I4").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A4:I9").format.borders = { preset: "inside", style: "thin", color: "#D8E1E8" };
sheet.getRange("A4:I9").format.borders = { preset: "outside", style: "thin", color: "#9DB2C2" };
sheet.getRange("A5:A9").format.numberFormat = "0";
sheet.getRange("B5:B9").format.numberFormat = "@";
sheet.getRange("E5:E9").format.numberFormat = "0";
sheet.getRange("F5:F9").format.numberFormat = "0.00";
sheet.getRange("G5:G9").format.numberFormat = "yyyy-mm-dd";
sheet.getRange("A5:A9").format.horizontalAlignment = "right";
sheet.getRange("E5:F9").format.horizontalAlignment = "right";

const widths = [12, 16, 15, 20, 11, 13, 14, 12, 25];
for (let index = 0; index < widths.length; index += 1) {
  sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidth = widths[index];
}
sheet.freezePanes.freezeRows(4);
sheet.tables.add("A4:I9", true, "TestOrdersTable");

const importSheet = workbook.worksheets.add("import_data");
importSheet.showGridLines = false;
importSheet.getRange("A1:I6").values = rows;
importSheet.getRange("A1:I1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
};
importSheet.getRange("A1:I6").format.borders = { preset: "inside", style: "thin", color: "#D8E1E8" };
importSheet.getRange("A1:I6").format.borders = { preset: "outside", style: "thin", color: "#9DB2C2" };
importSheet.getRange("A2:A6").format.numberFormat = "0";
importSheet.getRange("B2:B6").format.numberFormat = "@";
importSheet.getRange("E2:E6").format.numberFormat = "0";
importSheet.getRange("F2:F6").format.numberFormat = "0.00";
importSheet.getRange("G2:G6").format.numberFormat = "yyyy-mm-dd";
for (let index = 0; index < widths.length; index += 1) {
  importSheet.getRangeByIndexes(0, index, 1, 1).format.columnWidth = widths[index];
}
importSheet.freezePanes.freezeRows(1);
importSheet.tables.add("A1:I6", true, "ImportDataTable");

const check = await workbook.inspect({
  kind: "table",
  range: "test_orders!A4:I9",
  include: "values,formulas",
  tableMaxRows: 10,
  tableMaxCols: 10,
});
console.log(check.ndjson);

const preview = await workbook.render({
  sheetName: "test_orders",
  range: "A1:I9",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(`${outputDir}/tidb_test_orders_preview.png`, new Uint8Array(await preview.arrayBuffer()));

const importPreview = await workbook.render({
  sheetName: "import_data",
  range: "A1:I6",
  scale: 1.5,
  format: "png",
});
await fs.writeFile(`${outputDir}/tidb_test_orders_import_preview.png`, new Uint8Array(await importPreview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
