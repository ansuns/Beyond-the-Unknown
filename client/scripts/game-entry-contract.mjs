import ts from "typescript";

const COCOS_COMPONENT_METHODS = new Set([
  "schedule",
  "scheduleOnce",
  "unschedule",
  "unscheduleAllCallbacks",
  "getComponent",
  "getComponentInChildren",
  "getComponents",
  "getComponentsInChildren",
  "addComponent",
  "getChildByName",
  "getChildByPath",
  "getChildByUuid",
  "addChild",
  "removeChild",
  "removeAllChildren",
  "destroy",
  "isValid",
  "on",
  "off",
  "emit"
]);

function memberName(member) {
  const name = member.name;
  if (name && (ts.isIdentifier(name) || ts.isStringLiteral(name))) return name.text;
  return undefined;
}

export function findUndefinedThisCalls(sourceText, className = "GameEntry") {
  const source = ts.createSourceFile(
    "GameEntry.ts",
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS
  );
  const declaration = source.statements.find(
    (statement) => ts.isClassDeclaration(statement) && statement.name?.text === className
  );
  if (!declaration) return [`class ${className} was not found`];

  const members = new Set(
    declaration.members.map(memberName).filter((name) => typeof name === "string")
  );
  const errors = [];

  function visit(node) {
    if (ts.isCallExpression(node) &&
        ts.isPropertyAccessExpression(node.expression) &&
        node.expression.expression.kind === ts.SyntaxKind.ThisKeyword) {
      const name = node.expression.name.text;
      if (!members.has(name) && !COCOS_COMPONENT_METHODS.has(name)) {
        const position = source.getLineAndCharacterOfPosition(node.expression.name.getStart(source));
        errors.push(`undefined this.${name}() at line ${position.line + 1}`);
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(declaration);
  return errors;
}
