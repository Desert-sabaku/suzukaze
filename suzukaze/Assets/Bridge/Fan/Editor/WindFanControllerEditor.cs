using System;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace Suzukaze.Fan.Editor
{
    [CustomEditor(typeof(WindFanController))]
    [CanEditMultipleObjects]
    public sealed class WindFanControllerEditor : UnityEditor.Editor
    {
        // The test buttons go right before this field, i.e. between Test and Preset.
        private const string FirstPresetField = "preset";

        private SerializedProperty testResult;

        private void OnEnable() => testResult = serializedObject.FindProperty("testResult");

        // Keep the live preset values moving.
        public override bool RequiresConstantRepaint() => ((WindFanController)target).IsBlowing;

        public override void OnInspectorGUI()
        {
            Action<WindFanController> testAction = null;
            string testActionName = null;

            serializedObject.Update();
            SerializedProperty property = serializedObject.GetIterator();
            for (bool enterChildren = true; property.NextVisible(enterChildren); enterChildren = false)
            {
                if (property.name == FirstPresetField)
                {
                    DrawTestSection(ref testAction, ref testActionName);
                    EditorGUILayout.Space();
                }
                using (new EditorGUI.DisabledScope(property.propertyPath == "m_Script"))
                    EditorGUILayout.PropertyField(property, true);
            }
            serializedObject.ApplyModifiedProperties();

            // Run after the fields are applied so they do not overwrite the result.
            if (testAction != null)
            {
                foreach (Object selected in targets)
                {
                    var controller = (WindFanController)selected;
                    Undo.RecordObject(controller, testActionName);
                    testAction(controller);
                    PrefabUtility.RecordPrefabInstancePropertyModifications(controller);
                }
                SceneView.RepaintAll();
            }

            DrawPresetSection();
        }

        private void DrawTestSection(ref Action<WindFanController> action, ref string actionName)
        {
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Apply Test Wind"))
                    (action, actionName) = (c => c.ApplyTestWind(), "Apply Test Wind");
                if (GUILayout.Button("Stop Test Wind"))
                    (action, actionName) = (c => c.StopTestWind(), "Stop Test Wind");
            }

            if (serializedObject.isEditingMultipleObjects) return;
            EditorGUILayout.LabelField("Test Result", EditorStyles.boldLabel);
            for (int i = 0; i < testResult.arraySize; i++)
                EditorGUILayout.LabelField($"Fan {i}", testResult.GetArrayElementAtIndex(i).intValue.ToString());
        }

        private void DrawPresetSection()
        {
            EditorGUILayout.Space();
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Play Preset"))
                    foreach (Object selected in targets)
                        ((WindFanController)selected).PlayPreset();
                if (GUILayout.Button("Stop Wind"))
                    foreach (Object selected in targets)
                        ((WindFanController)selected).StopWind();
            }

            if (serializedObject.isEditingMultipleObjects) return;
            var wind = (WindFanController)target;
            if (!wind.IsBlowing) return;
            EditorGUILayout.LabelField("Blowing", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(true))
                EditorGUILayout.EnumPopup("Preset", wind.ActivePreset); // Shows the InspectorName.
            EditorGUILayout.LabelField("Power", wind.CurrentPower.ToString("0.00"));
            for (int i = 0; i < wind.CurrentOutput.Count; i++)
                EditorGUILayout.LabelField($"Fan {i}", wind.CurrentOutput[i].ToString());
        }
    }
}
