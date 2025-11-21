#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const ts = require("typescript");
const { parse } = require("@babel/parser");
const traverse = require("@babel/traverse").default;
const generate = require("@babel/generator").default;
const t = require("@babel/types");

function createProgram(filePath, tsconfigPath) {
  if (tsconfigPath && fs.existsSync(tsconfigPath)) {
    const configFile = ts.readConfigFile(tsconfigPath, ts.sys.readFile);
    if (configFile.error) {
      const message = ts.flattenDiagnosticMessageText(
        configFile.error.messageText,
        "\n"
      );
      throw new Error(`Failed to read tsconfig: ${message}`);
    }

    const config = ts.parseJsonConfigFileContent(
      configFile.config,
      ts.sys,
      path.dirname(tsconfigPath)
    );

    return ts.createProgram({
      rootNames: Array.from(new Set([filePath, ...config.fileNames])),
      options: config.options,
    });
  }

  return ts.createProgram({
    rootNames: [filePath],
    options: {
      allowJs: true,
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.Latest,
      moduleResolution: ts.ModuleResolutionKind.NodeJs,
      esModuleInterop: true,
    },
  });
}

function getQualifiedName(node) {
  if (t.isIdentifier(node)) {
    return node.name;
  }
  if (t.isTSQualifiedName(node)) {
    return `${getQualifiedName(node.left)}.${getQualifiedName(node.right)}`;
  }
  if (t.isTSImportEqualsDeclaration(node)) {
    return getQualifiedName(node.moduleReference);
  }
  return null;
}

function extractPropsFromTypeLiteral(literalNode) {
  const props = [];
  literalNode.members.forEach((member) => {
    if (!t.isTSPropertySignature(member)) {
      return;
    }
    if (!member.key) {
      return;
    }

    let name;
    if (t.isIdentifier(member.key)) {
      name = member.key.name;
    } else if (t.isStringLiteral(member.key)) {
      name = member.key.value;
    } else {
      return;
    }

    let type = "any";
    if (member.typeAnnotation) {
      type = generate(member.typeAnnotation.typeAnnotation).code;
    }

    props.push({
      name,
      type,
      required: !member.optional,
      defaultValue: null,
    });
  });
  return props;
}

function extractPropsFromTs(checker, sourceFile, typeName) {
  const props = [];
  function visit(node) {
    if (ts.isInterfaceDeclaration(node) && node.name.text === typeName) {
      node.members.forEach((member) => {
        if (!ts.isPropertySignature(member)) {
          return;
        }
        if (!member.name) {
          return;
        }

        const name = member.name.getText(sourceFile);
        const typeNode = member.type;
        const type = typeNode ? typeNode.getText(sourceFile) : "any";
        const required = !member.questionToken;

        props.push({
          name,
          type,
          required,
          defaultValue: null,
        });
      });
    } else if (
      ts.isTypeAliasDeclaration(node) &&
      node.name.text === typeName &&
      ts.isTypeLiteralNode(node.type)
    ) {
      node.type.members.forEach((member) => {
        if (!ts.isPropertySignature(member)) {
          return;
        }
        if (!member.name) {
          return;
        }
        const name = member.name.getText(sourceFile);
        const typeNode = member.type;
        const type = typeNode ? typeNode.getText(sourceFile) : "any";
        const required = !member.questionToken;

        props.push({
          name,
          type,
          required,
          defaultValue: null,
        });
      });
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return props;
}

function inferStateType(callExpression) {
  if (callExpression.typeParameters && callExpression.typeParameters.params.length > 0) {
    return generate(callExpression.typeParameters.params[0]).code;
  }
  if (callExpression.arguments.length === 0) {
    return "unknown";
  }
  const arg = callExpression.arguments[0];
  if (t.isBooleanLiteral(arg)) {
    return "boolean";
  }
  if (t.isStringLiteral(arg) || t.isTemplateLiteral(arg)) {
    return "string";
  }
  if (t.isNumericLiteral(arg)) {
    return "number";
  }
  if (t.isArrayExpression(arg)) {
    return "any[]";
  }
  if (t.isObjectExpression(arg)) {
    return "Record<string, unknown>";
  }
  return "unknown";
}

function getInitializerCode(node) {
  if (!node) {
    return null;
  }
  return generate(node).code;
}

function toNamespaceSet(namespaceIdentifiers) {
  if (!namespaceIdentifiers) {
    return new Set(["React"]);
  }
  if (namespaceIdentifiers instanceof Set) {
    return namespaceIdentifiers;
  }
  if (Array.isArray(namespaceIdentifiers)) {
    return new Set(namespaceIdentifiers);
  }
  return new Set([namespaceIdentifiers]);
}

function isMemberOrOptionalMemberExpression(node) {
  return (
    t.isMemberExpression(node) ||
    (typeof t.isOptionalMemberExpression === "function" &&
      t.isOptionalMemberExpression(node))
  );
}

function isReactHook(callee, hookName, namespaceIdentifiers) {
  const namespaces = toNamespaceSet(namespaceIdentifiers);

  if (t.isIdentifier(callee)) {
    return callee.name === hookName;
  }

  if (!isMemberOrOptionalMemberExpression(callee)) {
    return false;
  }

  const property = callee.property;
  const matchesProperty =
    (!callee.computed && t.isIdentifier(property, { name: hookName })) ||
    (callee.computed && t.isStringLiteral(property, { value: hookName }));

  if (!matchesProperty) {
    return false;
  }

  const object = callee.object;
  return t.isIdentifier(object) && namespaces.has(object.name);
}

function getHookNameFromCallee(callee, namespaceIdentifiers) {
  const namespaces = toNamespaceSet(namespaceIdentifiers);

  if (t.isIdentifier(callee)) {
    return callee.name;
  }

  if (!isMemberOrOptionalMemberExpression(callee)) {
    return null;
  }

  const object = callee.object;
  if (!t.isIdentifier(object) || !namespaces.has(object.name)) {
    return null;
  }

  const property = callee.property;
  if (!callee.computed && t.isIdentifier(property)) {
    return property.name;
  }
  if (callee.computed && t.isStringLiteral(property)) {
    return property.value;
  }

  return null;
}

function analyzeComponent(filePath, tsconfigPath) {
  const resolvedFile = path.resolve(filePath);
  const sourceCode = fs.readFileSync(resolvedFile, "utf8");
  const program = createProgram(resolvedFile, tsconfigPath);
  const checker = program.getTypeChecker();
  const sourceFile = program.getSourceFile(resolvedFile);
  if (!sourceFile) {
    throw new Error(`Unable to load source file: ${resolvedFile}`);
  }

  const ast = parse(sourceCode, {
    sourceType: "module",
    plugins: ["typescript", "jsx", "classProperties", "decorators-legacy"],
  });

  const namedPropTypes = new Set();
  const inlineProps = [];
  const propDefaults = new Map();
  const stateInfo = [];
  const hooks = [];
  const reactNamespaceIdentifiers = new Set(["React"]);
  const events = [];
  const childComponents = new Set();
  const imports = [];
  const exportInfo = {
    isDefault: false,
    isNamed: false,
    name: "",
  };
  let defaultExportName = null;
  let detectedComponentName = null;
  let isFunctional = false;
  let isClassComponent = false;

  function registerReactNamespace(name) {
    if (typeof name === "string" && name.length > 0) {
      reactNamespaceIdentifiers.add(name);
    }
  }

  function isReactNamespaceIdentifier(node) {
    return t.isIdentifier(node) && reactNamespaceIdentifiers.has(node.name);
  }

  function addHook(name, type, dependencies) {
    hooks.push({
      name,
      type,
      dependencies: dependencies && dependencies.length > 0 ? dependencies : [],
    });
  }

  function recordState(name, setter, initCode, stateType) {
    stateInfo.push({
      name,
      setter,
      initialValue: initCode,
      type: stateType,
    });
  }

  function recordEvent(handlerName, eventType, elementName) {
    events.push({
      name: handlerName,
      eventType,
      element: elementName || null,
    });
  }

  function processPropsFromParam(param, typeAnnotation) {
    if (t.isObjectPattern(param)) {
      param.properties.forEach((prop) => {
        if (t.isRestElement(prop)) {
          return;
        }

        const key = t.isIdentifier(prop.key)
          ? prop.key.name
          : t.isStringLiteral(prop.key)
          ? prop.key.value
          : null;
        if (!key) {
          return;
        }

        let defaultValue = null;
        if (t.isAssignmentPattern(prop.value)) {
          defaultValue = getInitializerCode(prop.value.right);
        }
        if (defaultValue === null && t.isAssignmentPattern(prop)) {
          defaultValue = getInitializerCode(prop.right);
        }
        if (defaultValue !== null) {
          propDefaults.set(key, defaultValue);
        }
      });
    }

    if (!typeAnnotation) {
      return;
    }

    const annotation = typeAnnotation.typeAnnotation;
    if (t.isTSTypeReference(annotation)) {
      const typeName = getQualifiedName(annotation.typeName);
      if (typeName) {
        const segments = typeName.split(".");
        namedPropTypes.add(segments[segments.length - 1]);
      }
    } else if (t.isTSTypeLiteral(annotation)) {
      extractPropsFromTypeLiteral(annotation).forEach((prop) => {
        inlineProps.push(prop);
      });
    }
  }

  traverse(ast, {
    ImportDeclaration(path) {
      const node = path.node;
      const importNames = [];
      let hasDefault = false;
      node.specifiers.forEach((specifier) => {
        if (t.isImportDefaultSpecifier(specifier)) {
          hasDefault = true;
          importNames.push(specifier.local.name);
          if (node.source.value === "react") {
            registerReactNamespace(specifier.local.name);
          }
        } else if (t.isImportSpecifier(specifier)) {
          importNames.push(specifier.local.name);
          if (
            node.source.value === "react" &&
            specifier.imported &&
            t.isIdentifier(specifier.imported, { name: "React" })
          ) {
            registerReactNamespace(specifier.local.name);
          }
        } else if (t.isImportNamespaceSpecifier(specifier)) {
          importNames.push("* as " + specifier.local.name);
          if (node.source.value === "react") {
            registerReactNamespace(specifier.local.name);
          }
        }
      });
      imports.push({
        source: node.source.value,
        imports: importNames,
        isDefault: hasDefault,
      });
    },
    TSImportEqualsDeclaration(path) {
      const node = path.node;
      if (!t.isIdentifier(node.id)) {
        return;
      }
      if (
        t.isTSExternalModuleReference(node.moduleReference) &&
        t.isStringLiteral(node.moduleReference.expression, { value: "react" })
      ) {
        registerReactNamespace(node.id.name);
      }
    },
    ExportDefaultDeclaration(path) {
      const decl = path.node.declaration;
      exportInfo.isDefault = true;
      if (t.isIdentifier(decl)) {
        defaultExportName = decl.name;
        exportInfo.name = decl.name;
      } else if (t.isFunctionDeclaration(decl) && decl.id) {
        detectedComponentName = decl.id.name;
        defaultExportName = decl.id.name;
        exportInfo.name = decl.id.name;
        isFunctional = true;
        if (decl.params.length > 0) {
          const param = decl.params[0];
          processPropsFromParam(param, decl.returnType || param.typeAnnotation);
        }
      } else if (t.isClassDeclaration(decl) && decl.id) {
        detectedComponentName = decl.id.name;
        defaultExportName = decl.id.name;
        exportInfo.name = decl.id.name;
        isClassComponent = true;
      }
    },
    ExportNamedDeclaration(path) {
      const { node } = path;
      exportInfo.isNamed = true;
      if (node.declaration && t.isFunctionDeclaration(node.declaration) && node.declaration.id) {
        detectedComponentName = node.declaration.id.name;
        if (!exportInfo.name) {
          exportInfo.name = node.declaration.id.name;
        }
      } else if (node.declaration && t.isClassDeclaration(node.declaration) && node.declaration.id) {
        detectedComponentName = node.declaration.id.name;
        if (!exportInfo.name) {
          exportInfo.name = node.declaration.id.name;
        }
        isClassComponent = true;
      } else if (node.specifiers && node.specifiers.length === 1) {
        const spec = node.specifiers[0];
        if (t.isExportSpecifier(spec) && t.isIdentifier(spec.exported)) {
          exportInfo.name = spec.exported.name;
        }
      }
    },
    ClassDeclaration(path) {
      const { node } = path;
      if (!node.id) {
        return;
      }
      const name = node.id.name;
      const extendsComponent =
        node.superClass &&
        ((t.isMemberExpression(node.superClass) &&
          isReactNamespaceIdentifier(node.superClass.object) &&
          t.isIdentifier(node.superClass.property) &&
          ["Component", "PureComponent"].includes(node.superClass.property.name)) ||
          (t.isIdentifier(node.superClass) &&
            ["Component", "PureComponent"].includes(node.superClass.name)));

      if (extendsComponent) {
        detectedComponentName = name;
        isClassComponent = true;
        if (
          node.superTypeParameters &&
          node.superTypeParameters.params &&
          node.superTypeParameters.params.length > 0
        ) {
          const propsType = node.superTypeParameters.params[0];
          const typeName = getQualifiedName(propsType);
          if (typeName) {
            const segments = typeName.split(".");
            namedPropTypes.add(segments[segments.length - 1]);
          } else if (t.isTSTypeReference(propsType)) {
            const simple = getQualifiedName(propsType.typeName);
            if (simple) {
              const segments = simple.split(".");
              namedPropTypes.add(segments[segments.length - 1]);
            }
          } else if (t.isTSTypeLiteral(propsType)) {
            extractPropsFromTypeLiteral(propsType).forEach((prop) => inlineProps.push(prop));
          }
        }
      }
    },
    VariableDeclarator(path) {
      const { node } = path;
      if (!t.isIdentifier(node.id)) {
        return;
      }
      const name = node.id.name;
      let isComponent = false;

      if (node.init && (t.isArrowFunctionExpression(node.init) || t.isFunctionExpression(node.init))) {
        isComponent = true;
        isFunctional = true;
        if (node.id.typeAnnotation && node.id.typeAnnotation.typeAnnotation) {
          const typeAnn = node.id.typeAnnotation.typeAnnotation;
          if (
            t.isTSTypeReference(typeAnn) &&
            t.isIdentifier(typeAnn.typeName) &&
            (typeAnn.typeName.name === "FC" || typeAnn.typeName.name === "FunctionComponent")
          ) {
            if (typeAnn.typeParameters && typeAnn.typeParameters.params.length > 0) {
              const first = typeAnn.typeParameters.params[0];
              if (t.isTSTypeReference(first)) {
                const refName = getQualifiedName(first.typeName);
                if (refName) {
                  const segments = refName.split(".");
                  namedPropTypes.add(segments[segments.length - 1]);
                }
              } else if (t.isTSTypeLiteral(first)) {
                extractPropsFromTypeLiteral(first).forEach((prop) => inlineProps.push(prop));
              }
            }
          } else if (
            t.isTSQualifiedName(typeAnn.typeName) &&
            t.isIdentifier(typeAnn.typeName.left) &&
            reactNamespaceIdentifiers.has(typeAnn.typeName.left.name) &&
            t.isIdentifier(typeAnn.typeName.right) &&
            typeAnn.typeName.right.name === "FC"
          ) {
            if (typeAnn.typeParameters && typeAnn.typeParameters.params.length > 0) {
              const first = typeAnn.typeParameters.params[0];
              if (t.isTSTypeReference(first)) {
                const refName = getQualifiedName(first.typeName);
                if (refName) {
                  const segments = refName.split(".");
                  namedPropTypes.add(segments[segments.length - 1]);
                }
              } else if (t.isTSTypeLiteral(first)) {
                extractPropsFromTypeLiteral(first).forEach((prop) => inlineProps.push(prop));
              }
            }
          }
        }

        if (node.init.params && node.init.params.length > 0) {
          const param = node.init.params[0];
          processPropsFromParam(param, param.typeAnnotation);
        }
      }

      if (node.init &&
          t.isCallExpression(node.init) &&
          t.isMemberExpression(node.init.callee) &&
          isReactNamespaceIdentifier(node.init.callee.object) &&
          t.isIdentifier(node.init.callee.property, { name: "forwardRef" })
      ) {
        isComponent = true;
        isFunctional = true;
      }

      if (isComponent && (!detectedComponentName || name === defaultExportName)) {
        detectedComponentName = name;
      }
    },
    FunctionDeclaration(path) {
      const { node } = path;
      if (!node.id) {
        return;
      }
      const name = node.id.name;
      if (!detectedComponentName) {
        detectedComponentName = name;
      }
      isFunctional = true;
      if (node.params && node.params.length > 0) {
        const param = node.params[0];
        processPropsFromParam(param, param.typeAnnotation);
      }
    },
    VariableDeclaration(path) {
      path.node.declarations.forEach((declarator) => {
        if (!t.isVariableDeclarator(declarator)) {
          return;
        }
        if (t.isIdentifier(declarator.id) && declarator.init) {
          if (
            t.isCallExpression(declarator.init) &&
            t.isIdentifier(declarator.init.callee, { name: "require" }) &&
            declarator.init.arguments.length > 0 &&
            t.isStringLiteral(declarator.init.arguments[0], { value: "react" })
          ) {
            registerReactNamespace(declarator.id.name);
          } else if (
            t.isMemberExpression(declarator.init) &&
            t.isCallExpression(declarator.init.object) &&
            t.isIdentifier(declarator.init.object.callee, { name: "require" }) &&
            declarator.init.object.arguments.length > 0 &&
            t.isStringLiteral(declarator.init.object.arguments[0], { value: "react" })
          ) {
            registerReactNamespace(declarator.id.name);
          }
        }

        if (!t.isArrayPattern(declarator.id)) {
          return;
        }
        if (!t.isCallExpression(declarator.init)) {
          return;
        }

        if (
          !isReactHook(
            declarator.init.callee,
            "useState",
            reactNamespaceIdentifiers
          )
        ) {
          return;
        }

        const elements = declarator.id.elements;
        if (!elements || elements.length < 2) {
          return;
        }
        const stateIdentifier = elements[0];
        const setterIdentifier = elements[1];
        if (!t.isIdentifier(stateIdentifier) || !t.isIdentifier(setterIdentifier)) {
          return;
        }
        const initialValue = declarator.init.arguments[0]
          ? getInitializerCode(declarator.init.arguments[0])
          : null;
        const stateType = inferStateType(declarator.init);
        recordState(
          stateIdentifier.name,
          setterIdentifier.name,
          initialValue,
          stateType
        );
        addHook("useState", "useState", []);
      });
    },
    CallExpression(path) {
      const { node } = path;
      const hookName = getHookNameFromCallee(
        node.callee,
        reactNamespaceIdentifiers
      );

      if (hookName && hookName.startsWith("use") && hookName !== "useState") {
        let hookType = "custom";
        if (hookName === "useEffect") hookType = "useEffect";
        else if (hookName === "useContext") hookType = "useContext";
        else if (hookName === "useRef") hookType = "useRef";
        else if (hookName === "useMemo") hookType = "useMemo";
        else if (hookName === "useCallback") hookType = "useCallback";

        const deps = [];
        if (node.arguments.length > 1) {
          const secondArg = node.arguments[1];
          if (t.isArrayExpression(secondArg)) {
            secondArg.elements.forEach((el) => {
              if (t.isIdentifier(el)) {
                deps.push(el.name);
              } else if (el) {
                deps.push(generate(el).code);
              }
            });
          }
        }
        addHook(hookName, hookType, deps);
      }
    },
    JSXAttribute(path) {
      const { node } = path;
      if (!t.isJSXIdentifier(node.name)) {
        return;
      }
      const attrName = node.name.name;
      if (!attrName.startsWith("on") || attrName.length <= 2) {
        return;
      }
      let handlerName = null;
      if (node.value && t.isJSXExpressionContainer(node.value)) {
        const expression = node.value.expression;
        if (t.isIdentifier(expression)) {
          handlerName = expression.name;
        } else if (t.isArrowFunctionExpression(expression)) {
          handlerName = "inline";
        } else {
          handlerName = generate(expression).code;
        }
      }
      const eventType = attrName.slice(2).toLowerCase();
      const parentElement = path.parent;
      let elementName = null;
      if (t.isJSXOpeningElement(parentElement) && t.isJSXIdentifier(parentElement.name)) {
        elementName = parentElement.name.name;
      }
      recordEvent(handlerName, eventType, elementName);
    },
    JSXOpeningElement(path) {
      const node = path.node;
      if (t.isJSXIdentifier(node.name)) {
        const name = node.name.name;
        if (name && /^[A-Z]/.test(name)) {
          childComponents.add(name);
        }
      } else if (t.isJSXMemberExpression(node.name)) {
        const parts = [];
        let current = node.name;
        while (t.isJSXMemberExpression(current)) {
          if (t.isJSXIdentifier(current.property)) {
            parts.unshift(current.property.name);
          }
          if (t.isJSXIdentifier(current.object)) {
            parts.unshift(current.object.name);
            break;
          }
          current = current.object;
        }
        if (parts.length > 0) {
          childComponents.add(parts.join("."));
        }
      }
    },
  });

  let props = [];
  const propMap = new Map();

  inlineProps.forEach((prop) => {
    const merged = {
      name: prop.name,
      type: prop.type,
      required: prop.required,
      defaultValue: propDefaults.get(prop.name) || prop.defaultValue,
      description: null,
    };
    propMap.set(prop.name, merged);
  });

  namedPropTypes.forEach((typeName) => {
    extractPropsFromTs(checker, sourceFile, typeName).forEach((prop) => {
      const existing = propMap.get(prop.name);
      const merged = {
        name: prop.name,
        type: prop.type,
        required: prop.required,
        defaultValue:
          (existing && existing.defaultValue) || propDefaults.get(prop.name) || null,
        description: null,
      };
      propMap.set(prop.name, merged);
    });
  });

  props = Array.from(propMap.values());

  const componentName = defaultExportName || detectedComponentName || "UnknownComponent";

  return {
    name: componentName,
    filePath: resolvedFile,
    props,
    state: stateInfo.map((state) => ({
      name: state.name,
      type: state.type,
      initialValue: state.initialValue,
      setter: state.setter,
    })),
    hooks,
    events,
    childComponents: Array.from(childComponents),
    imports,
    exports: {
      isDefault: exportInfo.isDefault,
      isNamed: exportInfo.isNamed,
      name: exportInfo.name || componentName,
    },
    isClassComponent,
    isFunctional,
  };
}

function main() {
  try {
    const args = process.argv.slice(2);
    if (args.length < 1) {
      throw new Error("Usage: react_analyzer_worker.js <filePath> [tsconfigPath]");
    }
    const filePath = args[0];
    const tsconfigPath = args[1] || null;
    const analysis = analyzeComponent(filePath, tsconfigPath);
    process.stdout.write(JSON.stringify(analysis));
  } catch (error) {
    process.stderr.write(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}

main();
